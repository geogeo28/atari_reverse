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
    (`include/gemdos/fs.h`) — the same three effects in Python, over the same image bytes.

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
import collections
import contextlib
import ctypes
import struct
import sys
from pathlib import Path

from harness import BASE_IMAGE, _lib, addrs, emu

import case
import gemdos
import staging
from address_hook import AddressHook
from opcodes import (ADDA_L_D0_A0, BTST_IMMEDIATE_STACK, DBF_D1, DBF_D2, LEA_ABSOLUTE_LONG_A0,
                     MOVE_B_A0_TO_A1, MOVE_B_A1_TO_A0, MOVE_L_ABSOLUTE_D0,
                     MOVE_W_IMMEDIATE_D2, MOVE_W_STACK_D0, MOVE_W_STACK_D1, MOVEA_L_STACK_A1,
                     MOVEQ_0_D0, MULU_W_IMMEDIATE_D0, RTS_WORD, SUBQ_W_1_D1)

# ---- the headers' constants, out of the C the cores compile against ------------------------------
# `include/gemdos/fs.h` holds the STRUCTURES (the wave's one-header-per-subsystem rule) and
# `include/addrs.h` the routine addresses; both are read by the one parser, exactly as
# `test/gemdos_memory.py` reads its group's header. The layers' own headers are read too — the drive
# builder's quirks (`drive()` below is the DMD as `$fc53c0` builds it) and the I/O engine's FAT12
# packing and seek modes — so every fs battery reads ONE namespace, this module's, and no battery
# keeps a dictionary of its own over a header. `gemdos/gemdos.h` is read for its HOST SLOTS, the frame
# locals the fs routines hand on (`test_gemdos_host_slots.py`).
_INCLUDE = Path(__file__).resolve().parents[1] / "include"
FS_HEADERS = tuple(_INCLUDE / name for name in ("gemdos/gemdos.h", "gemdos/fs.h", "gemdos/fs_drive.h",
                                                "gemdos/fs_io.h", "gemdos/fs_dir.h", "gemdos/fs_file.h",
                                                "gemdos/fs_leaves.h"))
CONSTANTS = {name: value for header in FS_HEADERS for name, value in addrs.parse(header).items()}
sys.modules[__name__].__dict__.update(CONSTANTS)

# ---- the span, and what is in it -----------------------------------------------------------------
# Above the declared staging band's top ($61000) and far below the stack guard, in the free window
# the snapshot leaves zero. `test_gemdos_fs_disk.py` is where both claims are checked.
RAM_DISK_AT = 0x68000
RAM_DISK_BYTES = 0xB000
# A USER BUFFER big enough for a transfer of whole clusters, which neither the 4 KB case band
# (claimed to its last byte) nor the RAM disk's own gap can hold: a FIFTH tenant of the captured
# machine's free window, taken the way the RAM disk took the fourth — by arithmetic
# `test_gemdos_fs_io.py` checks (dead RAM in the snapshot, clear of the RAM disk and of the stack
# guard). Growing `staging_bytes` would be the tidier answer, and is the orchestrator's.
USER_AT = 0x74000
USER_BYTES = 0x1000

# EVERY TENANT OF BOTH SPANS IS CLAIMED — `test/staging.py`'s `Registry`, the rule the declared band's
# batteries are held to, over the file system's window: the RAM disk and the user buffer above it.
# This module claims its own tenants below; a battery staging a buffer of its own claims it the same
# way (`test/fs_records.py` lays out the record gap), and an overlap between two claims is refused by
# name.
SPAN = staging.Registry(RAM_DISK_AT, USER_AT + USER_BYTES, "the file system's staged window")

BPB_AT = RAM_DISK_AT                            # the record `hdv_bpb` answers with
STUBS_AT = RAM_DISK_AT + 0x20                   # the three 68000 routines the vectors name
DRIVE_RECORDS_AT = RAM_DISK_AT + 0x100          # the staged drive's DMD, root DND and two OFDs
DRIVE_RECORDS_BYTES = 0x200                     # ...four of them at 0x40 apiece, and room to grow
# The 8.3 NAME battery's two FCB buffers and its text (`test_gemdos_fs_name.py`). They live HERE and
# not in `staging.SCRATCH` for one reason: the declared band's 4 KB is claimed to its last byte
# (`test/staging.py`'s registry), and this span has room the disk does not use. The battery stages no
# medium — it is in this module's span, not of it.
NAMES_BYTES = 0x100
NAMES_AT = SPAN.claim(DRIVE_RECORDS_AT + DRIVE_RECORDS_BYTES, NAMES_BYTES,
                      "test_gemdos_fs_name.py's FCB buffers")
BUFFERS_AT = RAM_DISK_AT + 0x400                # ...and the BCBs with their sector buffers
IMAGE_AT = RAM_DISK_AT + 0x2000                 # the disk itself
SPAN.claim(BPB_AT, STUBS_AT - BPB_AT, "the staged BPB and the two driver answers")
SPAN.claim(STUBS_AT, DRIVE_RECORDS_AT - STUBS_AT, "the three staged driver stubs")
SPAN.claim(DRIVE_RECORDS_AT, DRIVE_RECORDS_BYTES, "the staged drive's four records")
SPAN.claim(USER_AT, USER_BYTES, "the user buffer a transfer moves bytes to and from")

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
# and entry 1 the end-of-chain marker, so a data cluster is numbered from the header's
# `FIRST_DATA_CLUSTER`. The marker ON DISK is every one of an entry's twelve bits — what `$fc5f44`
# leaves of the -1 it is handed ($fc5fa4 `and.w #4095`), and what `$fc6038` turns back into -1.
FAT12_END_OF_CHAIN = GEMDOS_FAT12_ENTRY_MASK
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

ROOT_ENTRIES = ROOT_SECTORS * SECTOR_BYTES // DIRENT_BYTES

# A plain file's attribute: no bit set. Every bit this module writes is `include/gemdos/fs.h`'s.
ATTR_NONE = 0x00
# ...and two shapes of an attribute or mode ARGUMENT that no attribute bit names: a WORD whose high
# byte is not 0 (`Fattrib`, `create` and `Fcreate` keep only the low byte, `open` tests and stores the
# whole word), and bit 7 of the byte, which `ext.w` makes a sign.
ARGUMENT_HIGH_BYTE = 0x1200
ATTR_BIT_7 = 0x80

# What fills a staged buffer nothing else claims, so that a routine reading past what a case staged
# reads something a comparison notices rather than zeros. `vt52.CANARY`'s value, for its reason — and
# the ONE fill every fs battery pre-fills an output buffer with.
SLACK_FILL = 0xA5

# A D0 whose HIGH half none of the file system's routines writes, for the ones that return through a
# `move.w`/`clr.w` over the caller's (`include/gemdos/fs.h`, "what the cores export"): such a case
# enters with it, and the half it expects back is `callers_high_half(ENTRY_D0)`.
ENTRY_D0 = 0xDEC0_DE00
D0_LOW_WORD = 0xFFFF
LONG_MASK = 0xFFFF_FFFF                 # a Python int as the longword the 68000 holds


def callers_high_half(d0):
    """What a `clr.w d0` leaves of `d0`: its high half, the caller's."""
    return d0 & ~D0_LOW_WORD


def byte_swapped(value, fmt):
    """`value` as a word (`fmt` "H") or a long ("I") reads once `$fc4f10`/`$fc4f22` has turned it
    round — how a little-endian on-disk field reads on a 68000."""
    return int.from_bytes(struct.pack("<" + fmt, value), "big")


def as_stored(word):
    """An entry's little-endian time or date word as the 68000 reads it WITHOUT turning it round —
    how a DND (`$fc6616`) and an OFD (`$fc70da`) keep them (`include/gemdos/fs.h`)."""
    return byte_swapped(word, "H")


# ---- the three stubs -----------------------------------------------------------------------------
# ASSEMBLED OFFLINE by `m68k-elf-as -m68000` and transcribed here as the opcode words it produced,
# in the shape `test/gemdos.py`'s `slice_trampoline` uses: one `struct.pack`, each word named with
# the instruction it encodes. The source is below, and the BYTES are pinned by EXECUTION rather
# than by a reader: `test_gemdos_fs_disk.py`'s cases run the ROM's own `Rwabs` and `Mediach` through
# these bytes and check what arrived, and `test_gemdos_fs_drive.py`'s run `Getbpb` through them —
# its one caller is the drive log-in at `$fc67de`.
#
# EVERY STUB RUNS WITH A5 = 0 and has only D0-D2/A0-A2 to play with: the BIOS trap dispatcher at
# `$fc07fc` has already saved D3-D7/A3-A7 into the `savptr` frame and does `suba.l a5,a5` before its
# `jsr`, so a RAM-vector routine owes its caller nothing else.
#
#     hdv_bpb:                        | Getbpb(dev.w at 4(sp)) -> the LONGWORD the CASE poked:
#             move.l  GETBPB_ANSWER,d0 | the staged BPB by default, whatever the drive, or 0
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

# The two ANSWER stubs are one shape — `move.l <abs.l>,d0 / rts` — so they are one builder, eight
# bytes each.
ANSWER_STUB_BYTES = 8

# The three entry points, at fixed offsets inside the blob so that a poke of a vector and the stub
# it names cannot drift apart.
HDV_BPB_STUB = STUBS_AT
HDV_MEDIACH_STUB = HDV_BPB_STUB + ANSWER_STUB_BYTES
HDV_RW_STUB = HDV_MEDIACH_STUB + ANSWER_STUB_BYTES
# ...and the LONGWORD the media-change stub answers with, which is how a case drives the THREE-WAY
# protocol rather than only its "unchanged" arm. A longword and not a byte deliberately: `hdv_mediach`
# is an arbitrary driver's routine and the ROM TRUNCATES what it answers to a word ($fc5bd8
# `move.w d0,d5`), so a case has to be able to stage a high half for that truncation to be a fact.
# It sits just above the BPB record, in the same staged band.
ANSWER_BYTES = 4                                # every answer is a longword, the whole of D0
MEDIACH_ANSWER_AT = BPB_AT + BPB_BYTES
MEDIACH_ANSWER_BYTES = ANSWER_BYTES
# ...and the BPB POINTER the `Getbpb` stub answers with — `BPB_AT` unless a case stages another
# geometry, or 0, which is a drive with no medium and `$fc67de`'s ERROR arm.
GETBPB_ANSWER_AT = MEDIACH_ANSWER_AT + MEDIACH_ANSWER_BYTES
assert GETBPB_ANSWER_AT + ANSWER_BYTES <= STUBS_AT, "the two answers run into the stubs"

# Where each `Rwabs` argument sits once the BIOS dispatcher's `jsr` has pushed a return address: the
# function number is already gone, so the caller's first word is at 4(sp).
RWABS_RWFLAG_AT = 4
RWABS_BUFFER_AT = 6
RWABS_COUNT_AT = 10
RWABS_RECNO_AT = 12
RWABS_WRITE_BIT = 0

_RW_STUB_FORMAT = ">Hh H Hh HH HI H Hh H H H HHh H HH H Hh Hh H HH H Hh Hh H".replace(" ", "")


def _answer_stub(answer_at):
    """`move.l answer_at,d0 / rts` — a driver routine whose whole behaviour is a longword a case
    poked."""
    stub = struct.pack(">HIH", MOVE_L_ABSOLUTE_D0, answer_at, RTS_WORD)
    assert len(stub) == ANSWER_STUB_BYTES
    return stub


def stubs():
    """The three routines as one blob, to be poked at `STUBS_AT`."""
    blob = _answer_stub(GETBPB_ANSWER_AT) + _answer_stub(MEDIACH_ANSWER_AT)
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
    assert STUBS_AT + len(blob) <= DRIVE_RECORDS_AT, "the staged driver outgrew the band reserved for it"
    return {STUBS_AT: blob}


def mediach_answer(answer=None):
    """What the staged `hdv_mediach` is to answer — `addrs.MEDIACH_UNCHANGED` unless a case says
    otherwise, and the same byte the host hook reads, so the two shores cannot disagree."""
    return {MEDIACH_ANSWER_AT: struct.pack(
        ">I", addrs.MEDIACH_UNCHANGED if answer is None else answer)}


def getbpb_answer(answer=None):
    """...and what the staged `hdv_bpb` is to answer: the staged BPB's address unless a case says
    otherwise, read by the host hook out of the same longword."""
    return {GETBPB_ANSWER_AT: struct.pack(">I", BPB_AT if answer is None else answer)}


def vectors():
    """...and the three system variables that make the machine use them."""
    return {addrs.HDV_BPB: struct.pack(">I", HDV_BPB_STUB),
            addrs.HDV_RWABS: struct.pack(">I", HDV_RW_STUB),
            addrs.HDV_MEDIACH: struct.pack(">I", HDV_MEDIACH_STUB)}


def bpb_record():
    """The BPB `hdv_bpb` answers with: the nine words, in the order `include/gemdos/fs.h` names them.

    `fatrec` is the SECOND FAT's first record, which is TOS's convention and not a slip — `$fc5568`
    derives `m_recoff[0]` from it and `$fc59b2` writes the FIRST copy `m_fsiz` records lower.
    """
    return {BPB_AT: struct.pack(">9H", SECTOR_BYTES, SECTORS_PER_CLUSTER, CLUSTER_BYTES,
                                ROOT_SECTORS, FAT_SECTORS, FAT2_RECORD, DATA_RECORD,
                                DATA_CLUSTERS, 0)}


# ---- the records, built from the header's own offsets ---------------------------------------------
# field -> (header offset name, struct format). Big-endian: these are the ROM's in-memory records. A
# record is built WHOLE: every byte a case does not name is `fill`, so a field the routine should have
# written and did not reads as the fill rather than as a plausible zero. ONE set of builders for every
# fs battery — the staged drive below is built with them too — and a value is masked to its field's
# width, so a negative pseudo-cluster is staged as the word the ROM stores.
_NAME = f"{DIRENT_NAME_BYTES}s"
# The header spells the FCB's two fields as expressions over the entry's offsets, which the parser
# does not evaluate; these are the same two expressions over the offsets it did read.
FCB_STEM_BYTES = DIRENT_EXT
FCB_EXTENSION_BYTES = DIRENT_NAME_BYTES - DIRENT_EXT
DMD_FIELDS = {
    "recoff": ("DMD_RECOFF", ">3h"), "drvnum": ("DMD_DRVNUM", ">H"), "fsiz": ("DMD_FSIZ", ">H"),
    "clsiz": ("DMD_CLSIZ", ">H"), "clsizb": ("DMD_CLSIZB", ">H"), "recsiz": ("DMD_RECSIZ", ">H"),
    "numcl": ("DMD_NUMCL", ">H"), "clsiz_log2": ("DMD_CLSIZ_LOG2", ">H"),
    "clsiz_mask": ("DMD_CLSIZ_MASK", ">H"), "recsiz_log2": ("DMD_RECSIZ_LOG2", ">H"),
    "recsiz_mask": ("DMD_RECSIZ_MASK", ">H"), "clsizb_log2": ("DMD_CLSIZB_LOG2", ">H"),
    "fat_ofd": ("DMD_FAT_OFD", ">I"), "root_dnd": ("DMD_ROOT_DND", ">I"), "fat16": ("DMD_FAT16", ">H"),
}
DND_FIELDS = {
    "name": ("DND_NAME", _NAME), "strtcl": ("DND_STRTCL", ">H"), "time": ("DND_TIME", ">H"),
    "date": ("DND_DATE", ">H"), "ofd": ("DND_OFD", ">I"), "parent": ("DND_PARENT", ">I"),
    "child": ("DND_CHILD", ">I"), "sibling": ("DND_SIBLING", ">I"), "dmd": ("DND_DMD", ">I"),
    "parent_ofd": ("DND_PARENT_OFD", ">I"), "dirpos": ("DND_DIRPOS", ">I"),
    "scanned": ("DND_SCANNED", ">I"), "files": ("DND_FILES", ">I"),
}
OFD_FIELDS = {
    "link": ("OFD_LINK", ">I"), "flags": ("OFD_FLAGS", ">H"), "time": ("OFD_TIME", ">H"),
    "date": ("OFD_DATE", ">H"), "strtcl": ("OFD_STRTCL", ">H"), "fileln": ("OFD_FILELN", ">I"),
    "dmd": ("OFD_DMD", ">I"), "dir_dnd": ("OFD_DIR_DND", ">I"), "dir_ofd": ("OFD_DIR_OFD", ">I"),
    "dirpos": ("OFD_DIRPOS", ">I"), "pos": ("OFD_POS", ">I"), "curcl": ("OFD_CURCL", ">H"),
    "currec": ("OFD_CURREC", ">H"), "cloff": ("OFD_CLOFF", ">H"), "unused": ("OFD_UNUSED", ">H"),
    "next_same_file": ("OFD_NEXT_SAME_FILE", ">I"), "mode": ("OFD_MODE", ">H"),
}
_FIELD_MASKS = {">H": 0xFFFF, ">I": 0xFFFF_FFFF}


def _record(size, layout, fill, fields):
    record = bytearray([fill]) * size
    for field, value in fields.items():
        offset_name, fmt = layout[field]
        values = value if isinstance(value, tuple) else (value & _FIELD_MASKS.get(fmt, -1)
                                                         if isinstance(value, int) else value,)
        struct.pack_into(fmt, record, CONSTANTS[offset_name], *values)
    return bytes(record)


def dmd_bytes(fill=0, **fields):
    """One DMD, `DMD_BYTES` long; `fields` are `DMD_FIELDS`' keys, every other byte `fill`."""
    return _record(DMD_BYTES, DMD_FIELDS, fill, fields)


def dnd_bytes(fill=0, **fields):
    """...one DND."""
    return _record(DND_BYTES, DND_FIELDS, fill, fields)


def ofd_bytes(fill=0, **fields):
    """...one OFD."""
    return _record(OFD_BYTES, OFD_FIELDS, fill, fields)


def stage_dnd(at, fill=0, **fields):
    """A DND staged at `at`, as a poke."""
    return {at: dnd_bytes(fill, **fields)}


def stage_ofd(at, fill=0, **fields):
    """...and an OFD."""
    return {at: ofd_bytes(fill, **fields)}


def _field(image, at, layout, field):
    offset_name, fmt = layout[field]
    offset = at + CONSTANTS[offset_name]
    return struct.unpack_from(fmt, bytes(image[offset:offset + struct.calcsize(fmt)]))[0]


def dnd_field(image, at, field):
    """One field of the DND at `at`, out of any image a case holds (a run's final one, usually)."""
    return _field(image, at, DND_FIELDS, field)


def ofd_field(image, at, field):
    """...one field of an OFD."""
    return _field(image, at, OFD_FIELDS, field)


def fcb_name(name, extension=""):
    """The eleven-byte FCB form of a name: stem and extension space-padded, no dot."""
    return (name.ljust(FCB_STEM_BYTES)[:FCB_STEM_BYTES]
            + extension.ljust(FCB_EXTENSION_BYTES)[:FCB_EXTENSION_BYTES]).encode("latin-1")


def dirent_bytes(name, extension="", attr=0, cluster=0, length=0, time=0, date=0, deleted=False,
                 reserved=0):
    """One 32-byte directory entry, the DOS layout: little-endian from `DIRENT_TIME` on.

    `reserved` fills the ten DOS-reserved bytes between the attribute and the time, which no routine
    names — a case filling them with something non-zero sees a routine that copies too much.
    """
    entry = bytearray(fcb_name(name, extension) + bytes([attr])
                      + bytes([reserved]) * (DIRENT_TIME - DIRENT_ATTR - 1)
                      + struct.pack("<HHHI", time, date, cluster, length))
    if deleted:
        entry[DIRENT_NAME] = DIRENT_DELETED
    assert len(entry) == DIRENT_BYTES
    return bytes(entry)


# ---- the drive media descriptor, as `$fc53c0` builds it ------------------------------------------
# A STAGED INPUT, like the IOREC the ACIA battery stages — and a CHECKED one:
# `test_gemdos_fs_drive.py` runs the ROM's own builder over the staged BPB and requires the four
# records it cuts from the pool to be exactly `drive_records` at the addresses the pool gave it.
# Every value below is the ROM's own expression with this BPB's numbers in it, cited to the
# instruction that computes it.

def log2(value):
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

# The staged drive's four records, one pool record's worth of room apiece.
DRIVE_RECORD_STRIDE = 0x40
assert DND_BYTES == OFD_BYTES == DRIVE_RECORD_STRIDE, "a staged record no longer fits its slot"
DMD_AT, ROOT_DND_AT, ROOT_OFD_AT, FAT_OFD_AT = (DRIVE_RECORDS_AT + slot * DRIVE_RECORD_STRIDE
                                                for slot in range(4))


def root_dnd_bytes(root_ofd_at, dmd_at, **fields):
    """The root directory's DND as `$fc53c0` builds it, with `fields` over it (a child list, a mark)."""
    return dnd_bytes(**{"strtcl": ROOT_START_CLUSTER, "ofd": root_ofd_at, "dmd": dmd_at, **fields})


def root_ofd_bytes(dmd_at, **fields):
    """...and the root directory's pseudo-file, with `fields` over it (OFD_SCANNED)."""
    return ofd_bytes(**{"strtcl": ROOT_START_CLUSTER, "fileln": ROOT_SECTORS * SECTOR_BYTES, "dmd": dmd_at,
                        **fields})


def drive_records(number, dmd_at, root_dnd_at, root_ofd_at, fat_ofd_at, **dmd_fields):
    """The DMD, its root DND and the two pseudo-OFDs, for a drive of the geometry above, laid out
    for records at the four given addresses — each exactly as long as the pool record it models,
    and zero wherever `$fc53c0` stores nothing (the pool hands records out cleared).

    `dmd_fields` replaces DMD fields by `DMD_FIELDS` key — a drive of another geometry over the same
    records (`test/fs_io.py`'s FAT16 drive and four-sector clusters)."""
    dmd = dmd_bytes(**{
        "recoff": (RECOFF_FAT, RECOFF_DIR, RECOFF_DATA), "drvnum": number, "fsiz": FAT_SECTORS,
        "clsiz": SECTORS_PER_CLUSTER, "clsizb": CLUSTER_BYTES, "recsiz": SECTOR_BYTES,
        "numcl": DATA_CLUSTERS, "clsiz_log2": log2(SECTORS_PER_CLUSTER),
        "clsiz_mask": SECTORS_PER_CLUSTER - 1, "recsiz_log2": log2(SECTOR_BYTES),
        "recsiz_mask": SECTOR_BYTES - 1, "clsizb_log2": log2(CLUSTER_BYTES),
        "fat_ofd": fat_ofd_at, "root_dnd": root_dnd_at, **dmd_fields})
    root_dnd = root_dnd_bytes(root_ofd_at, dmd_at)
    root_ofd = root_ofd_bytes(dmd_at)
    # THE FAT PSEUDO-FILE STARTS AT POSITION 3, byte 3 of its cluster ($fc55be, $fc55ca) — the one
    # field this staging did not have until the builder's own output was compared against it.
    fat_ofd = ofd_bytes(strtcl=FAT_START_CLUSTER, fileln=FAT_SECTORS * SECTOR_BYTES, dmd=dmd_at,
                        pos=FAT_OFD_START_POSITION, cloff=FAT_OFD_START_POSITION)
    return {dmd_at: dmd, root_dnd_at: root_dnd, root_ofd_at: root_ofd, fat_ofd_at: fat_ofd}


def drive(number=0, **dmd_fields):
    """`drive_records` at this module's four staged slots."""
    return drive_records(number, DMD_AT, ROOT_DND_AT, ROOT_OFD_AT, FAT_OFD_AT, **dmd_fields)


def dmd_slot(drive):
    """Where the drive's DMD pointer lives in `GEMDOS_DMD_TABLE` — a signed index, as the ROM's is."""
    return addrs.GEMDOS_DMD_TABLE + drive * DRIVE_TABLE_ENTRY_BYTES


def node_slot(node):
    """...and a directory node's pointer in `GEMDOS_DIRECTORY_NODES`."""
    return addrs.GEMDOS_DIRECTORY_NODES + node * DRIVE_TABLE_ENTRY_BYTES


def curdir_at(drive):
    """The running process's `p_curdir` byte for `drive`."""
    return gemdos.BASEPAGE + addrs.BASEPAGE_CURDIR + drive


def dmd_pointer_poke(drive, dmd_at=DMD_AT):
    """`drive`'s table slot pointed at a DMD — the staged one unless a case says otherwise."""
    return {dmd_slot(drive): struct.pack(">I", dmd_at)}


def current_directory_poke(drive, node, dnd):
    """The running process's current directory on `drive`: its `p_curdir` byte naming `node`, and
    that node's slot pointing at `dnd`."""
    return {curdir_at(drive): bytes([node]), node_slot(node): struct.pack(">I", dnd)}


def record_of(region, record):
    """The BIOS record number `Rwabs` is called with for a record of `region` in the DMD's own
    pseudo-cluster space — the case's independent statement of what the cache should transfer."""
    return (RECOFF_FAT, RECOFF_DIR, RECOFF_DATA)[region] + record


def pseudo_record(cluster):
    """A cluster's first record in the DMD's own pseudo-cluster space, SIGNED — negative for the FAT
    and the root directory. Not a BIOS record: `record_of` makes one of it."""
    return cluster * SECTORS_PER_CLUSTER


def cluster_record(cluster):
    """...and the WORD `$fc55e6` answers for it, which is what an OFD's `OFD_CURREC` and a BCB's
    `BCB_BUFREC` hold."""
    return pseudo_record(cluster) & D0_LOW_WORD


# The first pseudo-record of each region, spelt once for every battery.
FAT_PSEUDO_RECORD = pseudo_record(FAT_START_CLUSTER)
ROOT_PSEUDO_RECORD = pseudo_record(ROOT_START_CLUSTER)
DATA_PSEUDO_RECORD = pseudo_record(FIRST_DATA_CLUSTER)


# ---- the buffer cache a case stages --------------------------------------------------------------
# Each BCB is a 20-byte record with a 512-byte buffer of its own, laid out so a case names one by
# index. The two list heads at `_bufl` are poked to whatever chains the case wants.
BCB_STRIDE = 0x220
BCB_COUNT = 6
BUFFER_OFFSET = 0x20
SPAN.claim(BUFFERS_AT, BCB_COUNT * BCB_STRIDE, "the staged BCBs and their sector buffers")


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


def linked(read_long, head_at, link, cap):
    """The records on a linked list after a run, head first: the head longword at `head_at`, each
    record's next at `+link`. `read_long(address)` is the run's own view of memory (`Result.long`).

    CAPPED one past `cap`, the most records a case can stage on it, so a list the run made circular or
    too long is a wrong ANSWER rather than a hang."""
    at = read_long(head_at)
    for _record in range(cap + 1):
        if at == 0:
            return
        yield at
        at = read_long(at + link)


def cache_order(read_long, which):
    """Which BCB indices list `which` holds AFTER a run, head first — so a case states the MRU order
    rather than three separate link longwords."""
    return [(at - BUFFERS_AT) // BCB_STRIDE
            for at in linked(read_long, addrs.SYSVAR_BUFL + which * addrs.SYSVAR_BUFL_ENTRY_BYTES, BCB_LINK,
                             BCB_COUNT)]


# ---- the disk image ------------------------------------------------------------------------------

# FAT12's twelve-bit PAIRS are what makes it awkward and what `$fc6038`/`$fc5f44` decode: entry `n`
# lives at byte `n + n/2`, in the low nibble-and-a-half for an even `n` and the high one for an odd
# one. The ROM reads the two bytes, BYTE-SWAPS them ($fc4f10) and then masks or shifts — which is how
# a big-endian 68000 reads a little-endian on-disk word. The encoder and the decoder are side by side
# and share the header's packing constants, so the staged FAT and a case's reading of it cannot drift.

def _fat12_pair_at(cluster):
    return cluster + cluster // 2


def fat12_table(entries):
    """`entries` (cluster -> value) as the FAT's sectors, LITTLE-endian twelve-bit pairs."""
    table = bytearray(FAT_SECTORS * SECTOR_BYTES)
    for cluster, value in sorted(entries.items()):
        at = _fat12_pair_at(cluster)
        pair = table[at] | (table[at + 1] << 8)
        value &= GEMDOS_FAT12_ENTRY_MASK
        if cluster & 1:
            pair = (pair & FAT12_ODD_KEEP) | (value << FAT12_ODD_SHIFT)
        else:
            pair = (pair & FAT12_EVEN_KEEP) | value
        struct.pack_into("<H", table, at, pair)
    return bytes(table)


def fat12_entry(table, cluster):
    """...and cluster `cluster`'s twelve-bit entry read back out of such a table, unsigned — the
    on-disk value, not the signed word `$fc6038` makes of an odd one."""
    pair = struct.unpack_from("<H", table, _fat12_pair_at(cluster))[0]
    return (pair >> FAT12_ODD_SHIFT) if cluster & 1 else (pair & GEMDOS_FAT12_ENTRY_MASK)


# One entry's fixed time and date VALUES — not the header's `DIRENT_TIME`/`DIRENT_DATE`, which are
# the two fields' OFFSETS. A value taken from the clock would be a byte no case chose.
STAGED_DIRENT_TIME = 0x1234
STAGED_DIRENT_DATE = 0x5678


def staged_dirent(name, extension="", attr=ATTR_NONE, cluster=0, length=0, deleted=False):
    """An entry as the staged disk writes every one: `dirent_bytes` with the staged time and date."""
    return dirent_bytes(name, extension, attr, cluster, length, time=STAGED_DIRENT_TIME,
                        date=STAGED_DIRENT_DATE, deleted=deleted)


def dots(cluster, parent_cluster):
    """The `.` and `..` a subdirectory opens with — `..` of a directory in the root naming cluster 0."""
    return [staged_dirent(".", "", GEMDOS_ATTR_SUBDIR, cluster), staged_dirent("..", "", GEMDOS_ATTR_SUBDIR, parent_cluster)]


SUBDIR_CLUSTER = 2
SHORT_CLUSTER = 3
SPAN_CLUSTER = 4
SHORT_BYTES = 100                       # inside one sector, and one cluster
SPAN_BYTES = 2500                       # crosses a sector AND a cluster: three clusters, 4 -> 5 -> 6
SPAN_CLUSTERS = -(-SPAN_BYTES // CLUSTER_BYTES)
# The six shapes the directory layer has to tell apart, in the order they appear in the root.
ROOT_FILES = (
    ("SUBDIR", "", GEMDOS_ATTR_SUBDIR, SUBDIR_CLUSTER, 0, False),
    ("SHORT", "TXT", ATTR_NONE, SHORT_CLUSTER, SHORT_BYTES, False),
    ("SPAN", "DAT", ATTR_NONE, SPAN_CLUSTER, SPAN_BYTES, False),
    ("EMPTY", "BIN", GEMDOS_ATTR_READ_ONLY, 0, 0, False),
    ("GONE", "OLD", ATTR_NONE, 0, 0, True),
    ("STAGEDDSK", "", GEMDOS_ATTR_VOLUME, 0, 0, False),
)


def index_by_name(rows):
    """`{name: index}` over directory rows in `ROOT_FILES`' shape — an entry's index is its byte
    position / 32, the `OFD_DIRPOS` an open copy of it holds and the position a search leaves."""
    return {name: index for index, (name, *_rest) in enumerate(rows)}


ROOT_INDEX = index_by_name(ROOT_FILES)


def body(seed, length):
    """A file's bytes: a ramp keyed on the file, so a read landing on the wrong cluster is a wrong
    BYTE rather than a plausible one."""
    return bytes((seed + index) & 0xFF for index in range(length))


# One seed per file, far enough apart that no two files' ramps share a byte value at the same
# offset — which is what makes "the read landed on the wrong cluster" a wrong byte.
SHORT_SEED = 0x11
SPAN_SEED = 0x40
SHORT_BODY = body(SHORT_SEED, SHORT_BYTES)
SPAN_BODY = body(SPAN_SEED, SPAN_BYTES)


def _write_both_fats(sectors, table):
    """`table` as BOTH FAT copies of `sectors`, in place — how a formatted disk has them."""
    for record in (FAT1_RECORD, FAT2_RECORD):
        sectors[record * SECTOR_BYTES:(record + FAT_SECTORS) * SECTOR_BYTES] = table


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

    fat = fat12_table({
        0: FAT_ENTRY_ZERO_PREFIX | MEDIA_DESCRIPTOR,
        1: FAT12_END_OF_CHAIN,
        SUBDIR_CLUSTER: FAT12_END_OF_CHAIN,
        SHORT_CLUSTER: FAT12_END_OF_CHAIN,
        SPAN_CLUSTER: SPAN_CLUSTER + 1,
        SPAN_CLUSTER + 1: SPAN_CLUSTER + 2,
        SPAN_CLUSTER + 2: FAT12_END_OF_CHAIN,
    })
    _write_both_fats(sectors, fat)

    root = bytearray(ROOT_SECTORS * SECTOR_BYTES)
    for index, entry in enumerate(ROOT_FILES):
        root[index * DIRENT_BYTES:(index + 1) * DIRENT_BYTES] = staged_dirent(*entry)
    sectors[ROOT_RECORD * SECTOR_BYTES:(ROOT_RECORD + ROOT_SECTORS) * SECTOR_BYTES] = root

    # `SUBDIR`'s own cluster: `.`, `..` and nothing else, which is what a search below the root
    # walks into.
    _write_cluster(sectors, SUBDIR_CLUSTER, b"".join(dots(SUBDIR_CLUSTER, 0)).ljust(CLUSTER_BYTES, b"\0"))
    _write_cluster(sectors, SHORT_CLUSTER, SHORT_BODY)
    for index in range(SPAN_CLUSTERS):
        _write_cluster(sectors, SPAN_CLUSTER + index,
                       SPAN_BODY[index * CLUSTER_BYTES:(index + 1) * CLUSTER_BYTES])
    return bytes(sectors)


DISK = _disk_image()
SPAN.claim(IMAGE_AT, DISK_BYTES, "the staged disk image")


def sector_of(source, record, at=0):
    """One sector out of the staged disk, or out of a run's final memory (`at=IMAGE_AT`)."""
    start = at + record * SECTOR_BYTES
    return bytes(source[start:start + SECTOR_BYTES])


# ---- VARIANTS of the staged disk ------------------------------------------------------------------
# Every FAT entry the base disk holds, read back out of its own FAT — the six-file layout above, which
# a variant keeps and adds to — and the one writer of a variant, so a battery that needs another FAT
# (a broken chain, a full disk, a directory tree) states only what differs.
FAT_ENTRIES = FIRST_DATA_CLUSTER + DATA_CLUSTERS


def fat_sectors(disk, first_record):
    """The FAT copy starting at `first_record`, out of a disk image."""
    at = first_record * SECTOR_BYTES
    return bytes(disk[at:at + FAT_SECTORS * SECTOR_BYTES])


BASE_FAT = {cluster: fat12_entry(fat_sectors(DISK, FAT1_RECORD), cluster) for cluster in range(FAT_ENTRIES)}
BASE_FAT_USED = {cluster for cluster, entry in BASE_FAT.items() if cluster >= FIRST_DATA_CLUSTER and entry != 0}


def with_fat(disk, table):
    """`disk` with `table` as BOTH FAT copies."""
    disk = bytearray(disk)
    _write_both_fats(disk, table)
    return disk


def disk(fat=None, clusters=None):
    """The staged disk with FAT12 entries changed (`{cluster: value}`, over the base ones) and data
    clusters overwritten (`{cluster: bytes}`). Returned as the poke at `IMAGE_AT` that replaces the
    base disk in `machine`."""
    image = with_fat(DISK, fat12_table({**BASE_FAT, **(fat or {})}))
    for cluster, contents in (clusters or {}).items():
        _write_cluster(image, cluster, contents)
    return {IMAGE_AT: bytes(image)}


# ---- the machine a file-system case starts from --------------------------------------------------

def machine(pokes=None):
    """Everything above, poked: the disk, the stubs, the three vectors and the BPB — plus
    `test/gemdos.py`'s own `machine()`, because every one of these routines reaches the BIOS and so
    needs `savptr` declared into the band the differential drops."""
    return gemdos.machine({IMAGE_AT: DISK, **stubs(), **vectors(), **bpb_record(),
                           **mediach_answer(), **getbpb_answer(), **(pokes or {})})


def user_buffer(contents=None):
    """The user buffer, pre-filled — `contents` at its start and `SLACK_FILL` after."""
    contents = contents or b""
    return {USER_AT: contents + bytes([SLACK_FILL]) * (USER_BYTES - len(contents))}


# ---- the candidate's half of the pair ------------------------------------------------------------
# `include/gemdos/fs.h`'s `recreate_call_disk_vector`, bound here for the process's lifetime through
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


def _staged_answer(buf, at):
    """The longword a case poked for an ANSWER stub, out of the candidate's own image."""
    return int.from_bytes(bytes(_span(buf, at, ANSWER_BYTES)), "big")


def _getbpb(buf, _rwflag, _buffer, _count, _recno, _dev):
    return _staged_answer(buf, GETBPB_ANSWER_AT)


def _mediach(buf, _rwflag, _buffer, _count, _recno, _dev):
    return _staged_answer(buf, MEDIACH_ANSWER_AT)


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


# ---- one case over the staged disk ----------------------------------------------------------------

class Result:
    """A run, and what the machine held AFTER it.

    `harness.differential` hands back the oracle's WRITE LEDGER rather than its final image, which
    is the sharper thing for a field the routine stores — a `KeyError` names a field nothing wrote
    — but the disk, the buffers and the list links are mostly bytes a case POKED and the routine
    left alone. So `final` is `case.final_image`: the captured snapshot, the case's pokes, and then
    the oracle's writes, composed once per run rather than per read.
    """

    def __init__(self, info, pokes):
        self.info = info
        self.staged = pokes
        self.final = case.final_image(info, pokes)

    def after(self, at, length):
        return bytes(self.final[at:at + length])

    def long(self, at):
        return int.from_bytes(self.after(at, 4), "big")

    def word(self, at):
        return int.from_bytes(self.after(at, 2), "big")

    def sector(self, record):
        """...and one sector of the staged disk."""
        return self.after(IMAGE_AT + record * SECTOR_BYTES, SECTOR_BYTES)

    def root_entry(self, index):
        """...and the 32 bytes of root entry `index` ON THE DISK — what a flush left there."""
        return self.after(IMAGE_AT + ROOT_RECORD * SECTOR_BYTES + index * DIRENT_BYTES, DIRENT_BYTES)

    def cluster_entry(self, cluster, index):
        """...and entry `index` of the directory whose first cluster is `cluster`, on the disk."""
        return self.after(IMAGE_AT + record_of_cluster(cluster) * SECTOR_BYTES + index * DIRENT_BYTES, DIRENT_BYTES)

    def order(self, which):
        return cache_order(self.long, which)


# WHY A CASE HERE DOES NOT POISON BY DEFAULT, said once for every fs battery. `case.run`'s
# attribution pass pre-inverts every byte the ORACLE wrote and re-runs both cores, and three things
# the oracle writes are pointers its next step FOLLOWS: `savptr`, which the oracle's real `trap #13`
# writes twice per BIOS call, so an inverted one sends the next save frame somewhere no case staged;
# a pool size class's CHAIN HEAD, which `$fc7f1a` both reads and writes; and a routine's own pointer
# argument it stores and then reads through (`$fc68dc`'s path pointer). A routine that reaches none of
# the three — no BIOS call, no pool, no stored pointer — poisons, and its battery says `poison=True`.
# What stands in for the pass otherwise is STAGING: every buffer starts full of `SLACK_FILL` and every
# record is filled, so a byte the reconstruction did not write reads as something no arm produces.

def run(entry, glue, pokes, *, regs=None, poison=False, **kwargs):
    """One differential over the staged disk: `machine(pokes)`, the driver staged, the candidate's
    disk traffic recorded, and a transfer off the disk refused. `regs` are the entry registers over
    A5 = 0 (the BIOS dispatcher's `suba.l a5,a5`, which every trap-reaching routine assumes);
    `kwargs` go to `case.run` (`width`, `max_insns`, ...)."""
    staged = machine(pokes)
    with staged_disk():
        info = case.run(entry, {"a5": 0, **(regs or {}), "_pokes": staged}, recording(glue),
                        poison=poison, **kwargs)
    return Result(info, staged)


# ---- one run's end, as the next run's start --------------------------------------------------------
# A SEQUENCE a program makes — `Fsfirst` then `Fsnext`, `Fdup` then two `Fclose`s — is proved one
# routine at a time, each run starting from the machine the one before it ENDED in. That is a real
# differential rather than a replay: the end state carried is the ORACLE's, and BOTH shores start the
# next run from it — a candidate that had ended anywhere else failed the previous run's compare.
#
# WHAT IS CARRIED: every staged poke re-read from the run's final memory (its staging with the
# oracle's writes over it), and each byte the oracle wrote that no poke covered. WHAT IS NOT: the stack
# band, which the differential drops and every run re-stages with its own arguments, and the fields
# `gemdos.machine` stages (`savptr`, the trap frame, the BIOS return slot), which the next run's
# `machine` fills afresh so that its own stores to them are still changes.
_STACK_BAND = range(emu.STACK_GUARD_LO, emu.STACK_BAND_HI)


def continued(result):
    """The pokes the run after `result` starts from — its end state, as above."""
    refilled = gemdos.machine().keys()
    covered = {address for at, data in result.staged.items() for address in range(at, at + len(data))}
    pokes = {at: result.after(at, len(data)) for at, data in result.staged.items()
             if at not in _STACK_BAND and at not in refilled}
    pokes.update({at: bytes([value]) for at, value in result.info["writes"].items()
                  if at not in covered and at not in _STACK_BAND})
    return pokes


# ---- a GEMDOS LEAF, entered at its own address or through the dispatcher -----------------------------
# Every file-system leaf, once: its selector, the handler address the ROM's dispatch table holds for
# it (`test_gemdos_fs_io_leaves.py` checks each against the table), its C core, and its argument frame
# as the ROM's caller lays it — a `struct` format, big-endian.
Leaf = collections.namedtuple("Leaf", "selector entry symbol frame")
FREAD = Leaf(addrs.GEMDOS_FREAD_FN, addrs.GEMDOS_FREAD, "gemdos_fread", ">hII")
FWRITE = Leaf(addrs.GEMDOS_FWRITE_FN, addrs.GEMDOS_FWRITE, "gemdos_fwrite", ">hII")
FSEEK = Leaf(addrs.GEMDOS_FSEEK_FN, addrs.GEMDOS_FSEEK, "gemdos_fseek", ">IhH")     # the offset first
FCLOSE = Leaf(addrs.GEMDOS_FCLOSE_FN, addrs.GEMDOS_FCLOSE, "gemdos_fclose", ">h")
FDATIME = Leaf(addrs.GEMDOS_FDATIME_FN, addrs.GEMDOS_FDATIME, "gemdos_fdatime", ">IhH")
DFREE = Leaf(addrs.GEMDOS_DFREE_FN, addrs.GEMDOS_DFREE, "gemdos_dfree", ">Ih")
DGETPATH = Leaf(addrs.GEMDOS_DGETPATH_FN, addrs.GEMDOS_DGETPATH, "gemdos_dgetpath", ">Ih")
FSNEXT = Leaf(addrs.GEMDOS_FSNEXT_FN, addrs.GEMDOS_FSNEXT, "gemdos_fsnext", ">")    # the DTA is its input
# ...and the leaves that find a NAME (`src/gemdos/fs_open.c`).
FSFIRST = Leaf(addrs.GEMDOS_FSFIRST_FN, addrs.GEMDOS_FSFIRST, "gemdos_fsfirst", ">IH")
DSETPATH = Leaf(addrs.GEMDOS_DSETPATH_FN, addrs.GEMDOS_DSETPATH, "gemdos_dsetpath", ">I")
FOPEN = Leaf(addrs.GEMDOS_FOPEN_FN, addrs.GEMDOS_FOPEN, "gemdos_fopen", ">IH")
FATTRIB = Leaf(addrs.GEMDOS_FATTRIB_FN, addrs.GEMDOS_FATTRIB, "gemdos_fattrib", ">IHH")
FDELETE = Leaf(addrs.GEMDOS_FDELETE_FN, addrs.GEMDOS_FDELETE, "gemdos_fdelete", ">I")
# ...and the leaves that make and unmake an entry (`src/gemdos/fs_create.c`).
FCREATE = Leaf(addrs.GEMDOS_FCREATE_FN, addrs.GEMDOS_FCREATE, "gemdos_fcreate", ">IH")
DDELETE = Leaf(addrs.GEMDOS_DDELETE_FN, addrs.GEMDOS_DDELETE, "gemdos_ddelete", ">I")
DCREATE = Leaf(addrs.GEMDOS_DCREATE_FN, addrs.GEMDOS_DCREATE, "gemdos_dcreate", ">I")
LEAVES = (FREAD, FWRITE, FSEEK, FCLOSE, FDATIME, DFREE, DGETPATH, FSNEXT, FSFIRST, DSETPATH, FOPEN, FATTRIB, FDELETE,
          FCREATE, DDELETE, DCREATE)
for _leaf in LEAVES:
    getattr(_lib, _leaf.symbol).restype = ctypes.c_uint32
_lib.gemdos_dispatch_selector.restype = ctypes.c_uint32


# THE SAME DOOR FOR A ROUTINE THAT IS NO LEAF. `sfirst`, `open` and `create` are in no dispatch table —
# a leaf (and `Frename`, `Pexec`) calls each by name — but each takes its arguments the way a leaf does,
# on the stack in its caller's frame. So each is a `Leaf` with NO SELECTOR, and a case enters it exactly
# as it enters a leaf at its own address (`leaf_pokes`, `leaf_glue`); `dispatch_slice` refuses one, there
# being nothing to dispatch.
def routine(entry, symbol, frame):
    """An unnumbered routine taking a leaf's frame, as a `Leaf` with no selector."""
    getattr(_lib, symbol).restype = ctypes.c_uint32
    return Leaf(None, entry, symbol, frame)


SFIRST = routine(addrs.GEMDOS_SFIRST, "gemdos_sfirst", ">IHI")
OPEN = routine(addrs.GEMDOS_OPEN, "gemdos_open", ">IH")
CREATE = routine(addrs.GEMDOS_CREATE, "gemdos_create", ">IH")


def leaf_pokes(leaf, values, pokes):
    """The case's pokes, then `values` laid out as the leaf's frame."""
    return {**pokes, **case.args(leaf.frame, *values)}


def leaf_glue(leaf, values):
    """...and our C core of the leaf over the same values."""
    return lambda lib, buf: getattr(lib, leaf.symbol)(buf, *values)


def argument_values(buf, arguments, frame):
    """The words the dispatcher copied, read back out of the CANDIDATE's image in `frame`'s shape —
    which is what proves our dispatcher passed the frame the leaf reads, rather than the case handing
    the leaf the values it hoped were there."""
    raw = ctypes.string_at(ctypes.addressof(buf.contents) + arguments, struct.calcsize(frame))
    return struct.unpack(frame, raw)


def leaf_handler(leaf):
    """The leaf's C core as the dispatcher's handler hook reaches it: handed the copied frame."""
    return lambda buf, arguments, _width: getattr(_lib, leaf.symbol)(buf, *argument_values(buf, arguments, leaf.frame))


def dispatch_slice(leaf, words, pokes):
    """A dispatcher slice (`gemdos.slice_pokes`) over the staged disk: our dispatcher calling our leaf
    through the hook, bound at the address the ROM's table holds, against the ROM's own dispatch of
    the same frame. `pokes` are the whole staging under the slice (a layer's cache and drive included).

    Not `gemdos.run_slice`: that policy poisons, and a run that reaches the BIOS cannot (`run` above).
    The handler calls it records are part of the claim — the leaf, exactly once."""
    assert leaf.selector is not None, f"{leaf.symbol} is no leaf: the dispatcher has no selector for it"

    def glue(lib, buf):
        return lib.gemdos_dispatch_selector(buf, gemdos.ARGUMENTS_AT)

    with gemdos.bound_handlers({leaf.entry: leaf_handler(leaf)}):
        result = run(gemdos.TRAMPOLINE_AT, gemdos.recording(glue), {**pokes, **gemdos.slice_pokes(leaf.selector, words)})
    assert [call[0] for call in gemdos.HANDLER_CALLS] == [leaf.entry]
    return result


# ---- the registry --------------------------------------------------------------------------------
# Every field these cases READ or POKE outside their own staged span, as `test_boot_snapshot.py`'s
# `CASE_FIELDS` takes them. The staged span is not here: it is RAM the snapshot leaves zero, which is
# a claim `test_gemdos_fs_disk.py` makes directly, and its tenants are `SPAN.claims`, which
# `test_boot_snapshot.py` splats once every battery has claimed its own.
#
# ...and each drive the SNAPSHOT has logged in: its DMD is in the pool arena, and a case that falls
# back to the drive's root node (`$fc67de`'s fresh directory, `$fc68dc`'s `\`) reads the pointer there.
_SNAPSHOT_DRIVES_OPENED = case.word_in(BASE_IMAGE, addrs.GEMDOS_DRIVES_OPENED)
_LOGGED_IN_ROOT_POINTERS = tuple(
    (case.long_in(BASE_IMAGE, dmd_slot(drive)) + DMD_ROOT_DND, DRIVE_TABLE_ENTRY_BYTES,
     f"drive {drive}'s root-node pointer, in the DMD the snapshot's pool holds")
    for drive in range(addrs.GEMDOS_DRIVE_COUNT) if _SNAPSHOT_DRIVES_OPENED >> drive & 1)
CASE_FIELDS = (
    *_LOGGED_IN_ROOT_POINTERS,
    (addrs.SYSVAR_BUFL, addrs.SYSVAR_BUFL_ENTRY_BYTES * BCB_LIST_COUNT,
     "the two buffer-cache list heads"),
    (addrs.HDV_BPB, 4, "the Getbpb RAM vector a case points at its own driver"),
    (addrs.HDV_RWABS, 4, "...and Rwabs'"),
    (addrs.HDV_MEDIACH, 4, "...and Mediach's"),
    (addrs.GEMDOS_DISK_ERROR, 4, "the last BIOS disk result, which every one of these stores"),
    (addrs.GEMDOS_DISK_ERROR_DRIVE, 2, "...and the drive it came from"),
    # ...and the drive tables the log-in reads and writes (`test_gemdos_fs_drive.py`): all forty
    # reference counts, where `test/gemdos_process.py` declares the sixteen a basepage reaches.
    (addrs.GEMDOS_DRIVES_OPENED, 2, "the logged-in drive mask"),
    (addrs.GEMDOS_DMD_TABLE, DRIVE_TABLE_ENTRY_BYTES * addrs.GEMDOS_DRIVE_COUNT, "each drive's DMD"),
    (addrs.GEMDOS_DIRECTORY_NODES, DRIVE_TABLE_ENTRY_BYTES * addrs.GEMDOS_DIRECTORY_NODE_COUNT,
     "the directory node table"),
    (addrs.GEMDOS_CURDIR_REFCOUNTS, addrs.GEMDOS_DIRECTORY_NODE_COUNT,
     "...and its reference counts, which the slot search reads"),
    (gemdos.BASEPAGE + addrs.BASEPAGE_CURDIR, addrs.BASEPAGE_CURDIR_ENTRIES, "the running process's p_curdir"),
)

# ...and the ROWS themselves go to `gemdos.register`, not to a list of this module's own: GEMDOS
# wave 1 made `gemdos.CASES` the one place every `trap #1` battery's rows land, and
# `test_boot_snapshot.py` splats it once. A second list here would be a second thing to splat.
