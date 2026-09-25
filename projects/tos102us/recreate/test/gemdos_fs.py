"""THE STAGED RAM DISK — how a GEMDOS file-system case gets a disk, on both shores at once.

Every other battery in this project proves a routine over the captured machine's own RAM. The file
system cannot be proved that way: its whole subject is a medium, and the captured machine's drive A:
holds a blank floppy no case may spin. So a case STAGES ONE.

WHAT MAKES THAT POSSIBLE is where GEMDOS stops. It makes no hardware access at all, and reaches a
disk through exactly three BIOS calls — `Rwabs`, `Getbpb`, `Mediach` — which are the dispatch
table's INDIRECT entries: entries 4, 7 and 9 have bit 31 set and `$fc0828`'s `movea.l (a0),a0`
turns each into a jump through a RAM VECTOR (`hdv_rw` $476, `hdv_bpb` $472, `hdv_mediach` $47e).
Those three longwords are ordinary system variables. A case pokes them — and from that moment the
ROM's own file system is running against a disk the case built, with no hardware touched by either
side and no model of a floppy anywhere.

THE PAIR IS THE SHAPE, exactly as `test/isr.py` stages a RAM vector for an interrupt handler:

  * for the ORACLE, three real 68000 stubs in this module's band, which copy sectors to and from an
    image poked into free RAM, answer a pointer to a staged BPB record, and answer the media-change
    byte the case poked (`mediach_answer` below, which is what makes the protocol's other two arms
    reachable at all);
  * for the CANDIDATE, the hook below, bound to `recreate_call_disk_vector`
    (`include/gemdos_fs.h`) — the same three effects in Python, over the same image bytes.

...and the DISK IS COMPARED IMAGE. The sectors, the buffer control blocks, their buffers and the
staged BPB all live in ordinary RAM inside the differential's byte compare, so "the ROM wrote this
sector and we did not" is an ordinary red diff rather than something the harness has to be taught
about. Nothing here is excluded and nothing is waived.

---- WHERE IT LIVES, AND HOW MUCH RAM IT IS -------------------------------------------------------

`project.toml` declares three tenants of the captured machine's free window ($1dde2..$f7fa1): the
run's stack at `stack_top` ($80000), Tier 3's cross-compiled blob at `bench_base` ($30000), and
`staging_base` ($60000), the 4 KB band a case stages buffers and stubs in. A FAT12 floppy does not
fit in 4 KB, so this module takes a FOURTH span of that same window — 44 KB at $68000, between the
staging band's top and the stack guard — and says so by ARITHMETIC rather than by prose:
`test_gemdos_fs_disk.py` asserts the span is clear of all three declared tenants AND that the
captured snapshot leaves every byte of it zero, which is the claim
`test_boot_snapshot.py::test_the_case_staging_band_is_dead_memory_in_this_snapshot` makes about the
declared band.

Growing `staging_bytes` instead would be the tidier answer and is the ORCHESTRATOR's to make:
`project.toml` is nobody's file during a wave, and `RomBench._vet_tenancy` is what would then refuse
an overlap automatically rather than these assertions doing it by hand.

---- THE DISK -------------------------------------------------------------------------------------

A real FAT12 floppy, built small enough to read whole in a failure message: 512-byte sectors, two
sectors per cluster, TWO sectors per FAT, two of root directory and 32 data clusters — 71 sectors,
36,352 bytes, 32 root entries. The layout is the ordinary DOS one, and the BPB the staged `hdv_bpb`
answers describes exactly it:

    sector 0        boot sector (a real BPB in its DOS fields; GEMDOS never reads it)
    sectors 1-2     FAT #1
    sectors 3-4     FAT #2          <- `fatrec`, because TOS's BPB names the SECOND copy
    sectors 5-6     root directory, 32 entries
    sectors 7..70   32 clusters of two sectors

BOTH FAT AND ROOT DIRECTORY ARE TWO SECTORS DELIBERATELY, and it is the one place the geometry is a
choice rather than a copy of a real floppy: a region whose length is not a whole number of CLUSTERS
leaves pseudo-records inside its own cluster span that map onto the region above it. That is legal
— an OFD's length stops the ROM ever reading them — and a needless trap for a case that spells a
record by hand, so the numbers are picked to make every pseudo-record of every region land on a real
sector of that region (`test_gemdos_fs_disk.py` asserts it).

The root directory holds a subdirectory, a file inside one cluster, a file that spans three, an
empty file, a deleted entry and a volume label — the six shapes the directory layer has to tell
apart. `SPAN.DAT`'s three-cluster chain (4 -> 5 -> 6) is what makes a read cross both a sector and a
cluster boundary in one call.
"""
import contextlib
import ctypes
import struct
import sys
from pathlib import Path

from harness import addrs

import gemdos
from address_hook import AddressHook
from opcodes import (ADDA_L_D0_A0, BTST_IMMEDIATE_STACK, DBF_D1, DBF_D2, LEA_ABSOLUTE_LONG_A0,
                     MOVE_B_A0_TO_A1, MOVE_B_A1_TO_A0, MOVE_L_A0_D0, MOVE_L_ABSOLUTE_D0,
                     MOVE_W_IMMEDIATE_D2, MOVE_W_STACK_D0, MOVE_W_STACK_D1, MOVEA_L_STACK_A1,
                     MOVEQ_0_D0, MULU_W_IMMEDIATE_D0, RTS_WORD, SUBQ_W_1_D1)

# ---- the two headers' constants, out of the C the cores compile against --------------------------
# `include/gemdos_fs.h` holds the STRUCTURES (the wave's one-header-per-subsystem rule) and
# `include/addrs.h` the routine addresses; both are read by the one parser, exactly as
# `test/gemdos_memory.py` reads its group's header.
GEMDOS_FS_HEADER = Path(__file__).resolve().parents[1] / "include" / "gemdos_fs.h"
CONSTANTS = addrs.parse(GEMDOS_FS_HEADER)
sys.modules[__name__].__dict__.update(CONSTANTS)

# ---- the span, and what is in it -----------------------------------------------------------------
# Above the declared staging band's top ($61000) and far below the stack guard, in the free window
# the snapshot leaves zero. `test_gemdos_fs_disk.py` is where both claims are checked.
RAM_DISK_AT = 0x68000
RAM_DISK_BYTES = 0xB000

BPB_AT = RAM_DISK_AT                            # the record `hdv_bpb` answers with
STUBS_AT = RAM_DISK_AT + 0x20                   # the three 68000 routines the vectors name
RECORDS_AT = RAM_DISK_AT + 0x100                # DMDs, DNDs and OFDs a case stages
RECORDS_BYTES = 0x200                           # ...four of them at 0x40 apiece, and room to grow
# The 8.3 NAME battery's two FCB buffers and its text (`test_gemdos_fs_name.py`). They live HERE and
# not in `staging.SCRATCH` for one reason: the declared band's 4 KB is claimed to its last byte
# (`test/staging.py`'s registry), and this span has room the disk does not use. The battery stages no
# medium — it is in this module's span, not of it.
NAMES_AT = RECORDS_AT + RECORDS_BYTES
NAMES_BYTES = 0x100
BUFFERS_AT = RAM_DISK_AT + 0x400                # ...and the BCBs with their sector buffers
IMAGE_AT = RAM_DISK_AT + 0x2000                 # the disk itself
assert NAMES_AT + NAMES_BYTES <= BUFFERS_AT, "the name battery's buffers reach into the BCBs'"

# ---- the geometry --------------------------------------------------------------------------------
SECTOR_BYTES = 512
SECTORS_PER_CLUSTER = 2
CLUSTER_BYTES = SECTOR_BYTES * SECTORS_PER_CLUSTER
# Two sectors each — the docstring says why.
FAT_SECTORS = 2
ROOT_SECTORS = 2
DATA_CLUSTERS = 32

BOOT_RECORD = 0
FAT1_RECORD = BOOT_RECORD + 1
FAT2_RECORD = FAT1_RECORD + FAT_SECTORS         # ...which is the BPB's `fatrec`
ROOT_RECORD = FAT2_RECORD + FAT_SECTORS
DATA_RECORD = ROOT_RECORD + ROOT_SECTORS
DISK_SECTORS = DATA_RECORD + DATA_CLUSTERS * SECTORS_PER_CLUSTER
DISK_BYTES = DISK_SECTORS * SECTOR_BYTES
assert IMAGE_AT - RAM_DISK_AT + DISK_BYTES <= RAM_DISK_BYTES

# FAT12's own constants. The first two entries are not clusters: entry 0 holds the media descriptor
# and entry 1 the end-of-chain marker, so a data cluster is numbered from 2.
FIRST_DATA_CLUSTER = 2
FAT_END_OF_CHAIN = 0xFFF
MEDIA_DESCRIPTOR = 0xF9                         # 80 tracks, double sided, 9 sectors
FAT_ENTRY_ZERO_PREFIX = 0xF00                   # ...and entry 0 is that byte under these bits
SECTORS_PER_TRACK = 9
HEADS = 2
FAT_COPIES = 2

# The DOS boot sector's own field offsets, for the one sector GEMDOS never reads: a jump, eight
# bytes of OEM name, then the BPB the on-disk format publishes — which has to agree with the one
# `hdv_bpb` answers, or the staged disk would describe two different geometries.
BOOT_BRANCH = 0
BOOT_BRANCH_BYTES = b"\xe9\x00\x00"           # `jmp` + nop, as DOS writes it
BOOT_OEM = 3
BOOT_OEM_BYTES = 8
BOOT_BPB = 11
BOOT_HEADS = 26

DIRENT_BYTES = 32
ROOT_ENTRIES = ROOT_SECTORS * SECTOR_BYTES // DIRENT_BYTES

# The directory attribute bits this module WRITES. `GEMDOS_ATTR_VOLUME` is in `include/gemdos_fs.h`
# instead, because the name layer's core compares against it.
ATTR_NONE = 0x00
ATTR_READ_ONLY = 0x01
ATTR_DIRECTORY = 0x10

# What fills a staged buffer nothing else claims, so that a routine reading past what a case staged
# reads something a comparison notices rather than zeros. `vt52.CANARY`'s value, for its reason.
SLACK_FILL = 0xA5


# ---- the three stubs -----------------------------------------------------------------------------
# ASSEMBLED OFFLINE by `m68k-elf-as -m68000` and transcribed here as the opcode words it produced,
# in the shape `test/gemdos.py`'s `slice_trampoline` uses: one `struct.pack`, each word named with
# the instruction it encodes. The source is below, and the BYTES are pinned by EXECUTION rather
# than by a reader: `test_gemdos_fs_disk.py`'s cases run the ROM's own `Rwabs` and `Mediach` through
# these bytes and check what arrived. `hdv_bpb`'s ten are the exception — NOTHING in this wave calls
# `Getbpb`, because the routine that does is the drive-media-descriptor builder at `$fc53c0` and it
# is not reconstructed. The vector is staged anyway: a machine with two of its three disk vectors
# pointed at a staged driver and the third at whatever the snapshot left is a machine nobody built,
# and the BPB record is where this module's DMD numbers come from either way.
#
# EVERY STUB RUNS WITH A5 = 0 and has only D0-D2/A0-A2 to play with: the BIOS trap dispatcher at
# `$fc07fc` has already saved D3-D7/A3-A7 into the `savptr` frame and does `suba.l a5,a5` before its
# `jsr`, so a RAM-vector routine owes its caller nothing else.
#
#     hdv_bpb:                        | Getbpb(dev.w at 4(sp)) -> the staged BPB, whatever the drive
#             lea     BPB_AT,a0
#             move.l  a0,d0
#             rts
#     hdv_mediach:                    | Mediach(dev.w) -> the LONGWORD the CASE poked below it
#             move.l  MEDIACH_ANSWER,d0
#             rts
#     hdv_rw:                         | Rwabs(rwflag.w, buffer.l, count.w, recno.w, dev.w)
#             movea.l 6(sp),a1        | the caller's buffer
#             moveq   #0,d0
#             move.w  12(sp),d0       | recno, unsigned
#             mulu.w  #512,d0
#             lea     IMAGE_AT,a0
#             adda.l  d0,a0           | -> the sector inside the staged image
#             move.w  10(sp),d1       | count
#             moveq   #0,d0           | ...and the result: 0, no error
#             subq.w  #1,d1
#             bmi.s   rw_done         | a count of 0 transfers nothing
#             btst    #0,5(sp)        | rwflag bit 0 is the direction, the only bit GEMDOS sets
#             bne.s   rw_write
#     rw_read:
#             move.w  #511,d2
#     1:      move.b  (a0)+,(a1)+
#             dbf     d2,1b
#             dbf     d1,rw_read
#             rts
#     rw_write:
#             move.w  #511,d2
#     1:      move.b  (a1)+,(a0)+
#             dbf     d2,1b
#             dbf     d1,rw_write
#     rw_done:
#             rts
# The instruction WORDS are `test/opcodes.py`'s — this stub is ordinary 68000 and had its own copy
# of sixteen of them. The two short branches below are not: they carry their displacement IN the
# opcode word, and both spans are fixed:
# every instruction between them is one the assembler cannot size differently.
BMI_S_TO_DONE = 0x6B26                  # bmi.s   rw_done   (+0x26 from the word after it)
BNE_S_TO_WRITE = 0x6610                 # bne.s   rw_write  (+0x10)
BACK_TO_THE_MOVE = -4                   # the inner `dbf`, to the `move.b` above it
BACK_TO_THE_SECTOR = -12                # ...and the outer one, to the `move.w #511,d2`

# The three entry points, at fixed offsets inside the blob so that a poke of a vector and the stub
# it names cannot drift apart.
HDV_BPB_STUB = STUBS_AT
HDV_MEDIACH_STUB = STUBS_AT + 0x0A
HDV_RW_STUB = STUBS_AT + 0x12
# ...and the LONGWORD the media-change stub answers with, which is how a case drives the THREE-WAY
# protocol rather than only its "unchanged" arm. A longword and not a byte deliberately: `hdv_mediach`
# is an arbitrary driver's routine and the ROM TRUNCATES what it answers to a word ($fc5bd8
# `move.w d0,d5`), so a case has to be able to stage a high half for that truncation to be a fact.
# It sits just above the BPB record, in the same staged band.
MEDIACH_ANSWER_AT = BPB_AT + BPB_BYTES
MEDIACH_ANSWER_BYTES = 4

# Where each `Rwabs` argument sits once the BIOS dispatcher's `jsr` has pushed a return address: the
# function number is already gone, so the caller's first word is at 4(sp).
RWABS_RWFLAG_AT = 4
RWABS_BUFFER_AT = 6
RWABS_COUNT_AT = 10
RWABS_RECNO_AT = 12
RWABS_WRITE_BIT = 0

_RW_STUB_FORMAT = ">Hh H Hh HH HI H Hh H H H HHh H HH H Hh Hh H HH H Hh Hh H".replace(" ", "")


def stubs():
    """The three routines as one blob, to be poked at `STUBS_AT`."""
    blob = struct.pack(">HIHH", LEA_ABSOLUTE_LONG_A0, BPB_AT, MOVE_L_A0_D0, RTS_WORD)
    blob += struct.pack(">HIH", MOVE_L_ABSOLUTE_D0, MEDIACH_ANSWER_AT, RTS_WORD)
    assert len(blob) == HDV_RW_STUB - STUBS_AT
    blob += struct.pack(
        _RW_STUB_FORMAT,
        MOVEA_L_STACK_A1, RWABS_BUFFER_AT,
        MOVEQ_0_D0,
        MOVE_W_STACK_D0, RWABS_RECNO_AT,
        MULU_W_IMMEDIATE_D0, SECTOR_BYTES,
        LEA_ABSOLUTE_LONG_A0, IMAGE_AT,
        ADDA_L_D0_A0,
        MOVE_W_STACK_D1, RWABS_COUNT_AT,
        MOVEQ_0_D0,
        SUBQ_W_1_D1,
        BMI_S_TO_DONE,
        BTST_IMMEDIATE_STACK, RWABS_WRITE_BIT, RWABS_RWFLAG_AT + 1,
        BNE_S_TO_WRITE,
        MOVE_W_IMMEDIATE_D2, SECTOR_BYTES - 1,
        MOVE_B_A0_TO_A1,
        DBF_D2, BACK_TO_THE_MOVE,
        DBF_D1, BACK_TO_THE_SECTOR,
        RTS_WORD,
        MOVE_W_IMMEDIATE_D2, SECTOR_BYTES - 1,
        MOVE_B_A1_TO_A0,
        DBF_D2, BACK_TO_THE_MOVE,
        DBF_D1, BACK_TO_THE_SECTOR,
        RTS_WORD)
    assert STUBS_AT + len(blob) <= RECORDS_AT, "the staged driver outgrew the band reserved for it"
    return {STUBS_AT: blob}


def mediach_answer(answer=None):
    """What the staged `hdv_mediach` is to answer — `addrs.MEDIACH_UNCHANGED` unless a case says
    otherwise, and the same byte the host hook reads, so the two shores cannot disagree."""
    return {MEDIACH_ANSWER_AT: struct.pack(
        ">I", addrs.MEDIACH_UNCHANGED if answer is None else answer)}


def vectors():
    """...and the three system variables that make the machine use them."""
    return {addrs.HDV_BPB: struct.pack(">I", HDV_BPB_STUB),
            addrs.HDV_RWABS: struct.pack(">I", HDV_RW_STUB),
            addrs.HDV_MEDIACH: struct.pack(">I", HDV_MEDIACH_STUB)}


def bpb_record():
    """The BPB `hdv_bpb` answers with: the nine words, in the order `include/gemdos_fs.h` names them.

    `fatrec` is the SECOND FAT's first record, which is TOS's convention and not a slip — `$fc5568`
    derives `m_recoff[0]` from it and `$fc59b2` writes the FIRST copy `m_fsiz` records lower.
    """
    return {BPB_AT: struct.pack(">9H", SECTOR_BYTES, SECTORS_PER_CLUSTER, CLUSTER_BYTES,
                                ROOT_SECTORS, FAT_SECTORS, FAT2_RECORD, DATA_RECORD,
                                DATA_CLUSTERS, 0)}


# ---- the drive media descriptor, as `$fc53c0` would build it -------------------------------------
# A STAGED INPUT, like the IOREC the ACIA battery stages: the builder is not reconstructed yet, so a
# case says what the machine held rather than running it. Every value below is the ROM's own
# expression with this BPB's numbers in it, cited to the instruction that computes it.

def _log2(value):
    """What `$fc539a` answers for a power of two — arithmetic here, and a verified core elsewhere."""
    return value.bit_length() - 1


ROOT_CLUSTERS = -(-ROOT_SECTORS // SECTORS_PER_CLUSTER)     # `(rdlen + clsiz - 1) / clsiz`, $fc54fe
FAT_CLUSTERS = -(-FAT_SECTORS // SECTORS_PER_CLUSTER)       # ...and the same for the FAT, $fc5528
ROOT_START_CLUSTER = -1 - ROOT_CLUSTERS                     # $fc5512
FAT_START_CLUSTER = ROOT_START_CLUSTER - FAT_CLUSTERS       # $fc554e
# ...and the three biases that turn a record in that pseudo-cluster space back into a BIOS record.
RECOFF_FAT = FAT2_RECORD - FAT_START_CLUSTER * SECTORS_PER_CLUSTER              # $fc5564
RECOFF_DIR = FAT2_RECORD + FAT_SECTORS - ROOT_START_CLUSTER * SECTORS_PER_CLUSTER  # $fc5580
RECOFF_DATA = DATA_RECORD - FIRST_DATA_CLUSTER * SECTORS_PER_CLUSTER            # $fc55a2

DMD_AT = RECORDS_AT
ROOT_DND_AT = RECORDS_AT + 0x40
ROOT_OFD_AT = RECORDS_AT + 0x80
FAT_OFD_AT = RECORDS_AT + 0xC0
RECORD_STRIDE = 0x40                                        # every staged record has room to spare


def drive(number=0):
    """The DMD, its root DND and the two pseudo-OFDs, for a drive of the geometry above."""
    dmd = bytearray(DMD_BYTES)
    struct.pack_into(">3h", dmd, DMD_RECOFF, RECOFF_FAT, RECOFF_DIR, RECOFF_DATA)
    struct.pack_into(">H", dmd, DMD_DRVNUM, number)
    struct.pack_into(">H", dmd, DMD_FSIZ, FAT_SECTORS)
    struct.pack_into(">H", dmd, DMD_CLSIZ, SECTORS_PER_CLUSTER)
    struct.pack_into(">H", dmd, DMD_CLSIZB, CLUSTER_BYTES)
    struct.pack_into(">H", dmd, DMD_RECSIZ, SECTOR_BYTES)
    struct.pack_into(">H", dmd, DMD_NUMCL, DATA_CLUSTERS)
    struct.pack_into(">H", dmd, DMD_CLSIZ_LOG2, _log2(SECTORS_PER_CLUSTER))
    struct.pack_into(">H", dmd, DMD_CLSIZ_MASK, SECTORS_PER_CLUSTER - 1)
    struct.pack_into(">H", dmd, DMD_RECSIZ_LOG2, _log2(SECTOR_BYTES))
    struct.pack_into(">H", dmd, DMD_RECSIZ_MASK, SECTOR_BYTES - 1)
    struct.pack_into(">H", dmd, DMD_CLSIZB_LOG2, _log2(CLUSTER_BYTES))
    struct.pack_into(">I", dmd, DMD_FAT_OFD, FAT_OFD_AT)
    struct.pack_into(">I", dmd, DMD_ROOT_DND, ROOT_DND_AT)

    dnd = bytearray(RECORD_STRIDE)
    struct.pack_into(">h", dnd, DND_STRTCL, ROOT_START_CLUSTER)
    struct.pack_into(">I", dnd, DND_OFD, ROOT_OFD_AT)
    struct.pack_into(">I", dnd, DND_DMD, DMD_AT)

    root_ofd = bytearray(RECORD_STRIDE)
    struct.pack_into(">h", root_ofd, OFD_STRTCL, ROOT_START_CLUSTER)
    struct.pack_into(">I", root_ofd, OFD_FILELN, ROOT_SECTORS * SECTOR_BYTES)
    struct.pack_into(">I", root_ofd, OFD_DMD, DMD_AT)

    fat_ofd = bytearray(RECORD_STRIDE)
    struct.pack_into(">h", fat_ofd, OFD_STRTCL, FAT_START_CLUSTER)
    struct.pack_into(">I", fat_ofd, OFD_FILELN, FAT_SECTORS * SECTOR_BYTES)
    struct.pack_into(">I", fat_ofd, OFD_DMD, DMD_AT)

    return {DMD_AT: bytes(dmd), ROOT_DND_AT: bytes(dnd), ROOT_OFD_AT: bytes(root_ofd),
            FAT_OFD_AT: bytes(fat_ofd)}


def record_of(region, record):
    """The BIOS record number `Rwabs` is called with for a record of `region` in the DMD's own
    pseudo-cluster space — the case's independent statement of what the cache should transfer."""
    return (RECOFF_FAT, RECOFF_DIR, RECOFF_DATA)[region] + record


# ---- the buffer cache a case stages --------------------------------------------------------------
# Each BCB is a 20-byte record with a 512-byte buffer of its own, laid out so a case names one by
# index. The two list heads at `_bufl` are poked to whatever chains the case wants.
BCB_STRIDE = 0x220
BCB_COUNT = 6
BUFFER_OFFSET = 0x20
assert BUFFERS_AT + BCB_COUNT * BCB_STRIDE <= IMAGE_AT


def bcb_at(index):
    return BUFFERS_AT + index * BCB_STRIDE


def buffer_at(index):
    return bcb_at(index) + BUFFER_OFFSET


def _bcb(index, link, holding):
    """One buffer control block and its buffer's contents.

    `holding` is `None` for an EMPTY buffer (`b_bufdrv == -1`) — what the ROM leaves after a flush,
    and what `GEMDOS_BUFFER_GET` prefers to evict — or `(drive, region, record, dirty, contents)`.
    """
    record_bytes = bytearray(BCB_BYTES)
    struct.pack_into(">I", record_bytes, BCB_LINK, link)
    struct.pack_into(">I", record_bytes, BCB_DM, DMD_AT)
    struct.pack_into(">I", record_bytes, BCB_BUFR, buffer_at(index))
    contents = None
    if holding is None:
        struct.pack_into(">H", record_bytes, BCB_BUFDRV, BCB_EMPTY)
    else:
        drive_number, region, record, dirty, contents = holding
        struct.pack_into(">H", record_bytes, BCB_BUFDRV, drive_number)
        struct.pack_into(">H", record_bytes, BCB_BUFTYP, region)
        struct.pack_into(">h", record_bytes, BCB_BUFREC, record)
        struct.pack_into(">H", record_bytes, BCB_DIRTY, dirty)
    return {bcb_at(index): bytes(record_bytes),
            buffer_at(index): contents if contents is not None
            else bytes([SLACK_FILL]) * SECTOR_BYTES}


def holding(drive_number=0, region=None, record=0, dirty=0, contents=None):
    """What a staged buffer is holding — the tuple `cache` below takes. `region` defaults to the one
    a non-negative record is in, which is the only one a data-list buffer can be."""
    return (drive_number, BCB_TYPE_DATA if region is None else region, record, dirty, contents)


EMPTY = None


def cache(fat=(), data=()):
    """The whole staged cache: two chains of `(index, holding)` pairs, in list order.

    Returns the BCB pokes AND the two `_bufl` head longwords, so a case's chain and the heads that
    name it cannot disagree.
    """
    pokes = {}
    heads = []
    for chain in (fat, data):
        heads.append(bcb_at(chain[0][0]) if chain else 0)
        for position, (index, held) in enumerate(chain):
            link = bcb_at(chain[position + 1][0]) if position + 1 < len(chain) else 0
            pokes.update(_bcb(index, link, held))
    pokes[addrs.SYSVAR_BUFL] = struct.pack(">2I", *heads)
    return pokes


def cache_order(read_long, which):
    """Which BCB indices list `which` holds AFTER a run, head first — so a case states the MRU order
    rather than three separate link longwords.

    `read_long(address)` is the run's own view of memory: the base image with the case's pokes and
    the oracle's writes over it (`test_gemdos_fs_disk.py`'s `Result`). The walk is capped at the
    number of BCBs a case can stage, so a list the run made circular is a wrong ANSWER rather than
    a hang.
    """
    at = read_long(addrs.SYSVAR_BUFL + which * addrs.SYSVAR_BUFL_ENTRY_BYTES)
    order = []
    while at != 0 and len(order) <= BCB_COUNT:
        order.append((at - BUFFERS_AT) // BCB_STRIDE)
        at = read_long(at + BCB_LINK)
    return order


# ---- the disk image ------------------------------------------------------------------------------

def _fat12(entries):
    """`entries` (cluster -> value) as one FAT sector, LITTLE-endian twelve-bit pairs.

    The pairs are what makes FAT12 awkward and what `$fc6038`/`$fc5f44` decode: entry `n` lives at
    byte `n + n/2`, in the low nibble-and-a-half for an even `n` and the high one for an odd one.
    The ROM reads the two bytes, BYTE-SWAPS them ($fc4f10) and then masks or shifts — which is how a
    big-endian 68000 reads a little-endian on-disk word.
    """
    table = bytearray(FAT_SECTORS * SECTOR_BYTES)
    for cluster, value in sorted(entries.items()):
        at = cluster + cluster // 2
        pair = table[at] | (table[at + 1] << 8)
        if cluster & 1:
            pair = (pair & 0x000F) | ((value & FAT_END_OF_CHAIN) << 4)
        else:
            pair = (pair & 0xF000) | (value & FAT_END_OF_CHAIN)
        table[at] = pair & 0xFF
        table[at + 1] = (pair >> 8) & 0xFF
    return bytes(table)


# One entry's fixed time and date. Nothing in this wave reads them, and a value taken from the clock
# would be a byte no case chose.
DIRENT_TIME = 0x1234
DIRENT_DATE = 0x5678


def _dirent(name, extension, attr, cluster, length, deleted=False):
    """One 32-byte directory entry: the 8.3 name, the attribute, ten reserved bytes, the time, the
    date, the first cluster and the length — the DOS layout, little-endian past the name."""
    stem = name.ljust(8)[:8].encode("ascii")
    if deleted:
        stem = bytes([DIRENT_DELETED]) + stem[1:]
    return (stem + extension.ljust(3)[:3].encode("ascii") + bytes([attr]) + bytes(10)
            + struct.pack("<HHHI", DIRENT_TIME, DIRENT_DATE, cluster, length))


SUBDIR_CLUSTER = 2
SHORT_CLUSTER = 3
SPAN_CLUSTER = 4
SHORT_BYTES = 100                       # inside one sector, and one cluster
SPAN_BYTES = 2500                       # crosses a sector AND a cluster: three clusters, 4 -> 5 -> 6
SPAN_CLUSTERS = -(-SPAN_BYTES // CLUSTER_BYTES)
# The six shapes the directory layer has to tell apart, in the order they appear in the root.
ROOT_FILES = (
    ("SUBDIR", "", ATTR_DIRECTORY, SUBDIR_CLUSTER, 0, False),
    ("SHORT", "TXT", ATTR_NONE, SHORT_CLUSTER, SHORT_BYTES, False),
    ("SPAN", "DAT", ATTR_NONE, SPAN_CLUSTER, SPAN_BYTES, False),
    ("EMPTY", "BIN", ATTR_READ_ONLY, 0, 0, False),
    ("GONE", "OLD", ATTR_NONE, 0, 0, True),
    ("STAGEDDSK", "", GEMDOS_ATTR_VOLUME, 0, 0, False),
)


def _body(seed, length):
    """A file's bytes: a ramp keyed on the file, so a read landing on the wrong cluster is a wrong
    BYTE rather than a plausible one."""
    return bytes((seed + index) & 0xFF for index in range(length))


# One seed per file, far enough apart that no two files' ramps share a byte value at the same
# offset — which is what makes "the read landed on the wrong cluster" a wrong byte.
SHORT_SEED = 0x11
SPAN_SEED = 0x40
SHORT_BODY = _body(SHORT_SEED, SHORT_BYTES)
SPAN_BODY = _body(SPAN_SEED, SPAN_BYTES)


def _write_cluster(sectors, cluster, contents):
    at = record_of_cluster(cluster) * SECTOR_BYTES
    sectors[at:at + len(contents)] = contents


def record_of_cluster(cluster):
    """Which BIOS record a data cluster starts at — the disk's own arithmetic, so a case can say
    what should have been transferred without asking the DMD."""
    return DATA_RECORD + (cluster - FIRST_DATA_CLUSTER) * SECTORS_PER_CLUSTER


def _disk_image():
    """The whole 36,352-byte floppy — `DISK_SECTORS` of them, laid out as the docstring says."""
    sectors = bytearray(DISK_BYTES)

    # Sector 0: a real boot sector. GEMDOS reads none of it — `Getbpb` is what answers — but a disk
    # whose own BPB disagreed with the staged one would be a trap for the next wave.
    boot = bytearray(SECTOR_BYTES)
    boot[BOOT_BRANCH:BOOT_BRANCH + len(BOOT_BRANCH_BYTES)] = BOOT_BRANCH_BYTES
    boot[BOOT_OEM:BOOT_OEM + BOOT_OEM_BYTES] = b"STAGED  "
    struct.pack_into("<HBHBHHBHH", boot, BOOT_BPB, SECTOR_BYTES, SECTORS_PER_CLUSTER, FAT1_RECORD,
                     FAT_COPIES, ROOT_ENTRIES, DISK_SECTORS, MEDIA_DESCRIPTOR, FAT_SECTORS,
                     SECTORS_PER_TRACK)
    struct.pack_into("<H", boot, BOOT_HEADS, HEADS)
    sectors[0:SECTOR_BYTES] = boot

    fat = _fat12({
        0: FAT_ENTRY_ZERO_PREFIX | MEDIA_DESCRIPTOR,
        1: FAT_END_OF_CHAIN,
        SUBDIR_CLUSTER: FAT_END_OF_CHAIN,
        SHORT_CLUSTER: FAT_END_OF_CHAIN,
        SPAN_CLUSTER: SPAN_CLUSTER + 1,
        SPAN_CLUSTER + 1: SPAN_CLUSTER + 2,
        SPAN_CLUSTER + 2: FAT_END_OF_CHAIN,
    })
    for at in (FAT1_RECORD, FAT2_RECORD):
        sectors[at * SECTOR_BYTES:(at + FAT_SECTORS) * SECTOR_BYTES] = fat

    root = bytearray(ROOT_SECTORS * SECTOR_BYTES)
    for index, entry in enumerate(ROOT_FILES):
        root[index * DIRENT_BYTES:(index + 1) * DIRENT_BYTES] = _dirent(*entry)
    sectors[ROOT_RECORD * SECTOR_BYTES:(ROOT_RECORD + ROOT_SECTORS) * SECTOR_BYTES] = root

    # `SUBDIR`'s own cluster: `.`, `..` and nothing else, which is what a search below the root
    # walks into.
    subdir = bytearray(CLUSTER_BYTES)
    subdir[0:DIRENT_BYTES] = _dirent(".", "", ATTR_DIRECTORY, SUBDIR_CLUSTER, 0)
    subdir[DIRENT_BYTES:2 * DIRENT_BYTES] = _dirent("..", "", ATTR_DIRECTORY, 0, 0)
    _write_cluster(sectors, SUBDIR_CLUSTER, bytes(subdir))
    _write_cluster(sectors, SHORT_CLUSTER, SHORT_BODY)
    for index in range(SPAN_CLUSTERS):
        _write_cluster(sectors, SPAN_CLUSTER + index,
                       SPAN_BODY[index * CLUSTER_BYTES:(index + 1) * CLUSTER_BYTES])
    return bytes(sectors)


DISK = _disk_image()


def sector_of(source, record, at=0):
    """One sector out of the staged disk, or out of a run's final memory (`at=IMAGE_AT`)."""
    start = at + record * SECTOR_BYTES
    return bytes(source[start:start + SECTOR_BYTES])


# ---- the machine a file-system case starts from --------------------------------------------------

def machine(pokes=None):
    """Everything above, poked: the disk, the stubs, the three vectors and the BPB — plus
    `test/gemdos.py`'s own `machine()`, because every one of these routines reaches the BIOS and so
    needs `savptr` declared into the band the differential drops."""
    return gemdos.machine({IMAGE_AT: DISK, **stubs(), **vectors(), **bpb_record(),
                           **mediach_answer(), **(pokes or {})})


# ---- the candidate's half of the pair ------------------------------------------------------------
# `include/gemdos_fs.h`'s `recreate_call_disk_vector`, bound here for the process's lifetime through
# `test/address_hook.py`'s record-and-refuse hook, keyed by BIOS FUNCTION NUMBER and recording
# (fn, rwflag, buffer, count, recno, dev) so a case can assert the ordered BIOS traffic.
DISK_CALL = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint16,
                             ctypes.c_uint16, ctypes.c_uint32, ctypes.c_uint16, ctypes.c_uint16,
                             ctypes.c_uint16)

_DISK_HOOK = AddressHook("recreate_call_disk_vector", DISK_CALL)
DISK_CALLS = _DISK_HOOK.calls
# ...and the transfers that asked for something outside the staged disk, which a case reports as its
# own failure beside the hook's refusals, because a ctypes callback cannot raise through to its caller.
OUT_OF_RANGE = []
recording = _DISK_HOOK.recording


def _span(buf, at, length):
    """`length` bytes of the CANDIDATE's image at `at`, as a sliceable ctypes array.

    A hook is handed the image as a `POINTER(c_uint8)`, which ctypes will not slice — and a whole
    sector copied one byte at a time (`test/isr.py`'s `poke`, which moves a handful) is 512 ctypes
    calls. Rebinding the same memory as an array of the right length costs one.
    """
    return (ctypes.c_uint8 * length).from_address(ctypes.addressof(buf.contents) + at)


def _getbpb(_buf, _rwflag, _buffer, _count, _recno, _dev):
    return BPB_AT


def _mediach(buf, _rwflag, _buffer, _count, _recno, _dev):
    return int.from_bytes(bytes(_span(buf, MEDIACH_ANSWER_AT, MEDIACH_ANSWER_BYTES)), "big")


def _rwabs(buf, rwflag, buffer, count, recno, _dev):
    # Byte for byte what the staged 68000 stub does — plus the bound the stub has not got.
    # A transfer outside the staged image would read the slack beyond it on the oracle's side and
    # host memory here, so it is refused rather than served, and the case is told which.
    # A count of 0 transfers nothing WHEREVER `recno` points — the stub's `subq.w #1 / bmi.s`
    # leaves before it touches anything — so it is not out of range however far off the disk it is.
    if count and recno + count > DISK_SECTORS:
        OUT_OF_RANGE.append((recno, count))
        return 0
    at = IMAGE_AT + recno * SECTOR_BYTES
    length = count * SECTOR_BYTES
    # A ctypes slice assignment copies through a temporary, where the stub is a forward byte copy:
    # the two differ only for a transfer whose buffer OVERLAPS the disk image, which no case stages
    # and the ROM could not ask for (a buffer inside the image would be a sector cached on top of
    # itself).
    source, destination = (buffer, at) if rwflag & (1 << RWABS_WRITE_BIT) else (at, buffer)
    _span(buf, destination, length)[:] = _span(buf, source, length)[:]
    return 0


# The staged driver's three vectors, the same on every case: what varies is the DISK, which is image.
_DRIVER = {addrs.BIOS_GETBPB_FN: _getbpb, addrs.BIOS_MEDIACH_FN: _mediach, addrs.BIOS_RWABS_FN: _rwabs}


def _describe_refused(refused):
    return (f"the candidate reached the disk door outside a candidate run, or with a function the staged "
            f"driver has not got: BIOS function(s) {sorted(set(refused))} were answered with a "
            f"fabricated 0, so whatever ran proved nothing")


@contextlib.contextmanager
def staged_disk():
    """The driver staged for ONE case, and the two refusals the callback could not raise reported on
    the way out: a call the hook refused, and a transfer off the staged disk."""
    OUT_OF_RANGE.clear()
    with _DISK_HOOK.staged(_DRIVER, _describe_refused):
        yield
    assert not OUT_OF_RANGE, (
        f"the candidate asked the staged disk for records outside it: {OUT_OF_RANGE} — the disk is "
        f"{DISK_SECTORS} sectors, so this case is about a machine neither shore modelled")


# ---- the registry --------------------------------------------------------------------------------
# Every field these cases READ or POKE outside their own staged span, as `test_boot_snapshot.py`'s
# `CASE_FIELDS` takes them. The staged span itself is not here: it is RAM the snapshot leaves zero,
# which is a claim `test_gemdos_fs_disk.py` makes directly.
CASE_FIELDS = (
    (addrs.SYSVAR_BUFL, addrs.SYSVAR_BUFL_ENTRY_BYTES * BCB_LIST_COUNT,
     "the two buffer-cache list heads"),
    (addrs.HDV_BPB, 4, "the Getbpb RAM vector a case points at its own driver"),
    (addrs.HDV_RWABS, 4, "...and Rwabs'"),
    (addrs.HDV_MEDIACH, 4, "...and Mediach's"),
    (addrs.GEMDOS_DISK_ERROR, 4, "the last BIOS disk result, which every one of these stores"),
    (addrs.GEMDOS_DISK_ERROR_DRIVE, 2, "...and the drive it came from"),
)

# ...and the ROWS themselves go to `gemdos.register`, not to a list of this module's own: GEMDOS
# wave 1 made `gemdos.CASES` the one place every `trap #1` battery's rows land, and
# `test_boot_snapshot.py` splats it once. A second list here would be a second thing to splat.
