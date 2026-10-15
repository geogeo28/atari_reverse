r"""BAND 6 WAVE 4, SLICE H: THE DEVICES (ruling W6-R9: DECLARED AT THE DRIVER'S ENTRIES, NOT POKED) — `aes_boot`'s
formatter, drive B: and printer, and the chains of `aes_desk.py`'s block "band 6 wave 4, slice H" that walk them.

Each device is held to THE ROM'S OWN RUN where one can be made — the ROM's Getbpb and Rwabs run in place over the
model's Floprd, and store what the model's own Getbpb and Rwabs store; the ROM's track builder run to its first FDC
access lays what the model's Flopfmt lays — and to THE ROM'S OWN INSTRUCTIONS where its run is the FDC's or the
port's (Flopfmt's frame, magic and mark; Flopwr's mark of a boot-sector write; the printer driver's hold-off and the
first instruction of its port transaction). And each is LABELLED: a run it answered names its class (`Boot.devices`).

NOTHING OF OURS RUNS HERE: every machine is one the ROM booted, with no blob in it.
"""
import struct

import pytest

from harness import BASE_IMAGE, addrs, emu, make_image

import st_build

import aes
import aes_boot
import aes_desk as desk
import aes_deskbind
import aes_objects
import case
from aes_boot import Refused

WORD_BYTES, LONG_BYTES, BUS = aes.WORD_BYTES, aes.LONG_BYTES, aes_boot.BUS
A, B = aes_boot.DRIVE_A, aes_boot.DRIVE_B_DEVICE
SECTOR = st_build.SECTOR_BYTES
BUFFER, STACK, SKEW = 0x60000, 0x6f000, 0x6e000     # free RAM of the DESKTOP.INF capture (held: `free_ram_of`)
STACK_BELOW = 0x400                     # how deep a routine's own frames go under its stack pointer, at most
RETURNED_TO = 0x6f800                   # the return address a ROM run is stopped at on arrival: never executed
ROM_RUN_INSNS = 200_000
SUPERVISOR_MASKED = aes_boot.SR_SUPERVISOR | addrs.SR_IPL_MASK


def rom_words(at, count):
    return struct.unpack_from(f">{count}H", BASE_IMAGE, at)


def free_ram_of(ram):
    assert not any(ram[BUFFER:RETURNED_TO + LONG_BYTES]), "the battery's buffer and stack are free RAM of this machine"
    return ram


def inf_memory(ram=None):
    memory = bytearray(BASE_IMAGE)
    memory[:aes_boot.RAM_BYTES] = free_ram_of(aes_boot.inf_preinit().ram if ram is None else ram)
    return memory


def entry_of(floppy, function):
    return next(at for at, each in floppy.served_at.items() if each == function)


def framed(memory, frame):
    """The dispatcher's `jsr` as it leaves a driver's routine: the return address at STACK, `frame` above it."""
    memory[STACK:STACK + LONG_BYTES + len(frame)] = struct.pack(">I", RETURNED_TO) + frame


def served(memory, floppy, function, frame):
    framed(memory, frame)
    answer, to = floppy.served(entry_of(floppy, function), STACK)
    assert to == RETURNED_TO
    return answer


def rom_s_own(memory, floppy, function, frame):
    """THE ROM'S OWN ROUTINE for `function`, run IN PLACE over `memory` from its entry to its return — the model
    serving only the driver's entries it calls (Floprd under Getbpb and Rwabs): D0 there."""
    framed(memory, frame)
    registers = {**aes_boot.inf_preinit().registers, "pc": entry_of(floppy, function), "sr": SUPERVISOR_MASKED,
                 "a7": STACK, "isp": STACK}
    run = aes_boot._Run(memory, floppy, ROM_RUN_INSNS, until=RETURNED_TO)
    try:
        run.to_an_idle(registers, {})
        answer = aes_boot._register("d0")
    finally:
        aes_boot._CPU.m68k_set_irq(aes_boot.NO_INTERRUPT)
        emu.bench_abort()
    return answer


def outside_the_stack(memory):
    """The megabyte less the band a routine's own frames are pushed in."""
    ram = bytes(memory[:aes_boot.RAM_BYTES])
    return ram[:STACK - STACK_BELOW], ram[STACK + LONG_BYTES * 4:]


def floprd_frame(buffer, device, sector, track, side, count):
    return struct.pack(">IIHHHHH", buffer, 0, device, sector, track, side, count)


# ---- THE FORMATTER: two more entries, read off the machine's own XBIOS --------------------------------------------------------------
# The operands the ROM's Flopfmt reads its frame by: its own four (`$fc1916`, `$fc1930..$fc1942`, off its SP as entered)
# and the shared prologue's, a `bsr` deeper (`$fc1c6c..$fc1c84`).
BSR_RETURN = LONG_BYTES
FLOPFMT_READS = {0xfc1916: (0x0caf, aes_boot.FLOPFMT_MAGIC_AT), 0xfc1930: (0x3b6f, aes_boot.FLOPFMT_SECTORS_AT),
                 0xfc1936: (0x3b6f, aes_boot.FLOPFMT_INTERLEAVE_AT), 0xfc193c: (0x3b6f, aes_boot.FLOPFMT_VIRGIN_AT),
                 0xfc1942: (0x2b6f, aes_boot.FLOPFMT_SKEW_AT)}
PROLOGUE_READS = {0xfc1c6c: (0x2b6f, aes_boot.FLOPFMT_BUFFER_AT), 0xfc1c72: (0x3b6f, aes_boot.FLOPFMT_DEVICE_AT),
                  0xfc1c7e: (0x3b6f, aes_boot.FLOPFMT_TRACK_AT), 0xfc1c84: (0x3b6f, aes_boot.FLOPFMT_SIDE_AT)}


def test_the_formatter_s_two_entries_are_the_rom_s_xbios_9_and_10_and_its_frame_the_one_the_rom_reads():
    """Flopwr and Flopfmt are the routines the machine's own XBIOS table names, served beside the four (which stay
    four); Flopfmt's frame is where the ROM's own instructions read it — the magic first, compared before the FDC is
    touched; Flopwr's is Floprd's (one prologue)."""
    memory = inf_memory()
    floppy = aes_boot.Floppy(memory, aes_boot.inf_disk_of())
    assert floppy.formatter == {aes_boot._xbios_entry(memory, aes_boot.XBIOS_FLOPWR): aes_boot.FLOPWR,
                                aes_boot._xbios_entry(memory, aes_boot.XBIOS_FLOPFMT): aes_boot.FLOPFMT}
    assert len(floppy.entries) == 4 and floppy.served_at == {**floppy.entries, **floppy.formatter}
    assert entry_of(floppy, aes_boot.FLOPFMT) == aes_boot.FLOPFMT_MAGIC_CHECK_AT
    assert struct.unpack_from(">I", BASE_IMAGE, aes_boot.FLOPFMT_MAGIC_CHECK_AT + WORD_BYTES)[0] == aes_boot.FLOPFMT_MAGIC
    for at, (opcode, offset) in FLOPFMT_READS.items():
        displacement_at = at + WORD_BYTES + (LONG_BYTES if opcode == 0x0caf else 0)
        assert (rom_words(at, 1)[0], rom_words(displacement_at, 1)[0]) == (opcode, offset)
    for at, (opcode, offset) in PROLOGUE_READS.items():
        assert rom_words(at, 2) == (opcode, offset + BSR_RETURN)


def test_flopfmt_and_flopwr_mark_the_drive_changed_where_the_rom_s_do():
    """FLOPFMT MARKS THE DRIVE CHANGED before it formats (`moveq #2,d0; bsr` the mode store), and FLOPWR where its
    write begins at the boot sector (`sector - 1 | track | side` zero); the mode store is the driver's modes plus the
    device — the byte `aes_boot.driver_mode` reads off Rwabs."""
    memory = inf_memory()
    assert rom_words(aes_boot.FLOPFMT_MARKS_THE_DRIVE_AT, 3) == (0x7002, 0x6100, aes_boot.THE_MODE_STORE - aes_boot.FLOPFMT_MARKS_THE_DRIVE_AT - 4)
    assert rom_words(aes_boot.FLOPWR_MARKS_THE_BOOT_SECTOR_AT, 11) == (
        0x302d, 0x0a0c, 0x5340, 0x806d, 0x0a0a, 0x806d, 0x0a0e, 0x6606, 0x7002, 0x6100, 0x0680)
    assert aes_boot.FLOPWR_MARKS_THE_BOOT_SECTOR_AT + 18 + WORD_BYTES + 0x0680 == aes_boot.THE_MODE_STORE
    assert rom_words(aes_boot.THE_MODE_STORE, 3) == (0x41f9, *struct.unpack(">2H", struct.pack(">I", aes_boot.driver_mode(memory) - A)))


def test_the_track_the_model_lays_is_the_rom_s_own_builder_s():
    """THE ROM'S TRACK BUILDER (`$fc198c`) run in the oracle to its first FDC access (`$fc1a54`), its globals as
    Flopfmt's prologue stores them: the buffer it leaves is `aes_boot.track_laid`'s, byte for byte — the desk's skew
    tables (its interleave table rotated) on two tracks, both sides."""
    skews = ([1, 4, 7, 2, 5, 8, 3, 6, 9], [3, 6, 9, 1, 4, 7, 2, 5, 8])
    for track, side, order, virgin in ((0, 0, skews[0], 0xe5e5), (79, 1, skews[1], 0xe5e5), (40, 1, skews[0], 0x1234)):
        globals_ = {0xa12: struct.pack(">I", BUFFER), 0xa1c: struct.pack(">I", SKEW), 0xa16: struct.pack(">H", len(order)),
                    0xa18: struct.pack(">h", -1), 0xa1a: struct.pack(">H", virgin), 0xa0a: struct.pack(">H", track),
                    0xa0e: struct.pack(">H", side), SKEW: struct.pack(f">{len(order)}H", *order)}
        image = make_image({0: aes_boot.inf_preinit().ram, **globals_})
        final, _writes, _regs = emu.run(image, TRACK_BUILDER, {"a5": 0}, stop_pc=TRACK_BUILDER_FIRST_FDC_ACCESS)
        laid = aes_boot.track_laid(track, side, order, virgin)
        assert bytes(final[BUFFER:BUFFER + len(laid)]) == laid and not any(final[BUFFER + len(laid):BUFFER + len(laid) + SECTOR])


TRACK_BUILDER, TRACK_BUILDER_FIRST_FDC_ACCESS = 0xfc198c, 0xfc1a54
VERIFY_ADDS_A_SECTOR_AT, VERIFY_ENDS_THE_LIST_AT = 0xfc1b08, 0xfc1ba6


def flopfmt_frame(track, side, order=tuple(range(1, 10)), magic=aes_boot.FLOPFMT_MAGIC, interleave=-1, virgin=0xe5e5, device=A):
    return struct.pack(">IIHHHHhIH", BUFFER, SKEW, device, len(order), track, side, interleave, magic, virgin)


def test_flopfmt_formats_the_side_of_the_track_and_leaves_the_buffer_as_the_rom_s_verify_does():
    """THE MODEL'S FLOPFMT: the side's nine sectors the virgin word over (the rest of the disk as it was), the drive
    marked CHANGED, and the buffer the track laid — then the verify's (its reads into the buffer's second 512 bytes,
    `addi.l #512` at `$fc1b08`; the bad-sector list's end at the head, `clr.w (a2)` at `$fc1ba6`). The labelled
    class is the formatter's. REFUSED BY NAME: another magic, an interleave, a skew table not the nine sectors."""
    assert rom_words(VERIFY_ADDS_A_SECTOR_AT, 4) == (0x06ad, 0x0000, aes_boot.VERIFY_READS_AT, 0x0a12)
    assert rom_words(VERIFY_ENDS_THE_LIST_AT, 1) == (0x4252,)
    memory, disk = inf_memory(), aes_boot.inf_disk_of()
    floppy = aes_boot.Floppy(memory, disk)
    order = (2, 4, 6, 8, 1, 3, 5, 7, 9)
    memory[SKEW:SKEW + 2 * len(order)] = struct.pack(">9H", *order)
    assert served(memory, floppy, aes_boot.FLOPFMT, flopfmt_frame(5, 1, order)) == 0
    at = (5 * st_build.HEADS + 1) * st_build.SECTORS_PER_TRACK * SECTOR
    track_bytes = st_build.SECTORS_PER_TRACK * SECTOR
    assert floppy.disk[at:at + track_bytes] == aes_boot.virgin_sector(0xe5e5) * st_build.SECTORS_PER_TRACK
    assert floppy.disk[:at] == disk[:at] and floppy.disk[at + track_bytes:] == disk[at + track_bytes:]
    assert floppy.changed() and floppy.labelled == {aes_boot.THE_FORMATTER}
    laid = aes_boot.track_laid(5, 1, order, 0xe5e5)
    left = bytes(memory[BUFFER:BUFFER + len(laid)])
    assert left[:WORD_BYTES] == bytes(WORD_BYTES) and left[WORD_BYTES:SECTOR] == laid[WORD_BYTES:SECTOR]
    assert left[SECTOR:2 * SECTOR] == aes_boot.virgin_sector(0xe5e5) and left[2 * SECTOR:] == laid[2 * SECTOR:]
    for frame in (flopfmt_frame(5, 1, order, magic=0), flopfmt_frame(5, 1, order, interleave=1),
                  flopfmt_frame(st_build.TRACKS, 0, order)):
        with pytest.raises(Refused, match="the model formats the desk's track alone"):
            served(memory, floppy, aes_boot.FLOPFMT, frame)
    memory[SKEW:SKEW + 2 * len(order)] = struct.pack(">9H", *(1,) * len(order))
    with pytest.raises(Refused, match="the model formats the desk's track alone"):
        served(memory, floppy, aes_boot.FLOPFMT, flopfmt_frame(5, 1, order))


def test_flopwr_writes_the_sectors_and_only_a_boot_sector_write_marks_the_drive():
    memory = inf_memory()
    floppy = aes_boot.Floppy(memory, aes_boot.inf_disk_of())
    memory[BUFFER:BUFFER + 2 * SECTOR] = bytes(range(256)) * 4
    assert served(memory, floppy, aes_boot.FLOPWR, floprd_frame(BUFFER, A, 3, 7, 1, 2)) == 0
    at = ((7 * st_build.HEADS + 1) * st_build.SECTORS_PER_TRACK + 2) * SECTOR
    assert floppy.disk[at:at + 2 * SECTOR] == bytes(range(256)) * 4 and not floppy.changed()
    assert served(memory, floppy, aes_boot.FLOPWR, floprd_frame(BUFFER, A, 1, 7, 1, 1)) == 0 and not floppy.changed()
    # (sector 1 of track 0's SECOND side — the disk copy writes it before the boot sector: no boot sector, no mark)
    assert served(memory, floppy, aes_boot.FLOPWR, floprd_frame(BUFFER, A, 1, 0, 1, 1)) == 0 and not floppy.changed()
    assert served(memory, floppy, aes_boot.FLOPWR, floprd_frame(BUFFER, A, 1, 0, 0, 1)) == 0
    assert floppy.disk[:SECTOR] == bytes(range(256)) * 2 and floppy.changed()
    assert [call.function for call in floppy.calls] == [aes_boot.FLOPWR] * 4
    with pytest.raises(Refused, match="Flopwr of drive 1: the model holds drive A: alone"):
        served(memory, floppy, aes_boot.FLOPWR, floprd_frame(BUFFER, B, 1, 0, 0, 1))


def test_a_format_of_drive_b_formats_and_marks_drive_b_alone():
    """THE FRAME'S DEVICE DECIDES (no chain formats B: — the desk's Format is A:'s): Flopfmt of drive 1 formats drive
    B:'s image and marks B: CHANGED, drive A:'s disk and mode as they were; the classes drive B:'s and the formatter's."""
    memory, disk = inf_memory(), aes_boot.inf_disk_of()
    floppy = aes_boot.Floppy(memory, disk, aes_boot.blank_disk())
    order = tuple(range(1, st_build.SECTORS_PER_TRACK + 1))
    memory[SKEW:SKEW + WORD_BYTES * len(order)] = struct.pack(f">{len(order)}H", *order)
    mode_of_a = memory[aes_boot.driver_mode(memory)]
    assert served(memory, floppy, aes_boot.FLOPFMT, flopfmt_frame(3, 0, order, virgin=0x1234, device=B)) == 0
    at = 3 * st_build.HEADS * st_build.SECTORS_PER_TRACK * SECTOR
    assert floppy.held_in_b()[at:at + st_build.SECTORS_PER_TRACK * SECTOR] == aes_boot.virgin_sector(0x1234) * st_build.SECTORS_PER_TRACK
    assert floppy.disk == disk and memory[aes_boot.driver_mode(memory)] == mode_of_a != aes_boot.MEDIA_CHANGED
    assert memory[aes_boot.driver_mode(memory) + B] == aes_boot.MEDIA_CHANGED
    assert floppy.labelled == {aes_boot.DRIVE_B, aes_boot.THE_FORMATTER}


# ---- THE VERIFY OF A WRITE: what the ROM's Rwabs's Flopver leaves in the driver's buffer -------------------------------------------
# `$fc1426..$fc1448`: `tst.w _fverify; beq` past; the write's frame pushed again with the buffer `$16da`; `jsr` Flopver.
FLOPVER, FLOPVER_CALLS_ITS_BODY_AT = 0xfc1ae2, 0xfc1af8       # (its prologue, then `bsr.s` the body)
RWABS_VERIFIES = (0x4a79, 0x0000, aes_boot.SYSVAR_FVERIFY, 0x6736, 0x3e83, 0x3f05, 0x3f06, 0x3f04, 0x3f2e, 0x0010, 0x42a7,
                  0x2f3c, 0x0000, aes_boot.RWABS_VERIFY_BUFFER, 0x4eb9, *struct.unpack(">2H", struct.pack(">I", FLOPVER)))
FLOPVER_S_BODY = 0xfc1afe               # Flopfmt's verify too: its sectors read at the buffer + 512, the list's zero at the head
BSR_S_TO_THE_BODY = 0x6104
NOT_LAID = 0x77


def test_a_verified_rwabs_write_leaves_the_driver_s_buffer_as_the_rom_s_verify_leaves_it():
    """THE ROM'S RWABS VERIFIES EACH WRITE WHERE `_fverify` IS SET (`$fc1426`) — Flopver of the sectors just written,
    into the driver's buffer `$16da`, whose body is Flopfmt's verify's (`$fc1afe`: each sector read into the buffer's
    second 512 bytes, the bad-sector list's zero at its head — pinned with Flopfmt's). The model lays what it leaves:
    over FORMATTED's own three flag-3 writes (their counts and records read off the chain's ledger, `_fverify` set on
    its machine), the zero word at `$16da` and THE LAST RECORD WRITTEN at `$18da`; with `_fverify` clear, nothing
    there. (No run of the ROM's verify itself can be made: it is the FDC's.)"""
    assert rom_words(aes_boot.RWABS_VERIFY_AT, len(RWABS_VERIFIES)) == RWABS_VERIFIES
    assert rom_words(FLOPVER_CALLS_ITS_BODY_AT, 1) == (BSR_S_TO_THE_BODY,)
    assert FLOPVER_CALLS_ITS_BODY_AT + WORD_BYTES + (BSR_S_TO_THE_BODY & aes.BYTE_MASK) == FLOPVER_S_BODY
    assert FLOPVER_S_BODY < VERIFY_ADDS_A_SECTOR_AT < VERIFY_ENDS_THE_LIST_AT
    rwabs = [call.arguments for step in desk.walked(desk.FORMATTED).steps for call in step.boot.floppy if call.function == aes_boot.RWABS]
    writes = [(count, record) for flag, _buffer, count, record, _device in rwabs
              if flag == aes_boot.RWABS_NO_MEDIA_CHECK + aes_boot.RWABS_WRITE]
    assert writes == [(7, 11), (5, 1), (5, 6)]
    verify = slice(aes_boot.RWABS_VERIFY_BUFFER, aes_boot.RWABS_VERIFY_BUFFER + 2 * SECTOR)
    for count, record in writes:
        for fverify in (True, False):
            memory, disk = formatted_memory()
            assert case.word_in(memory, aes_boot.SYSVAR_FVERIFY)
            if not fverify:
                memory[aes_boot.SYSVAR_FVERIFY:aes_boot.SYSVAR_FVERIFY + WORD_BYTES] = bytes(WORD_BYTES)
            memory[BUFFER:BUFFER + count * SECTOR] = b"".join(bytes((nth + 1,)) * SECTOR for nth in range(count))
            memory[verify] = bytes((NOT_LAID,)) * (2 * SECTOR)
            frame = struct.pack(">HIHHH", aes_boot.RWABS_NO_MEDIA_CHECK + aes_boot.RWABS_WRITE, BUFFER, count, record, A)
            assert served(memory, aes_boot.Floppy(memory, disk), aes_boot.RWABS, frame) == 0
            left = bytes(memory[verify])
            if fverify:
                assert left == bytes(WORD_BYTES) + bytes((NOT_LAID,)) * (SECTOR - WORD_BYTES) + bytes((count,)) * SECTOR
            else:
                assert left == bytes((NOT_LAID,)) * (2 * SECTOR)


# ---- THE DISK FORMATTED: what the ROM's format wrote through the formatter and Rwabs -------------------------------------------------
FAT_HEAD = bytes((0xf7, 0xff, 0xff, 0x00))     # `$fedd14`, `$fedd18`: the FAT's first two words, the rest cleared
VOLUME_LABEL_ATTRIBUTE_AT = 11                 # `$fedcb2`: `move.w #8,10(a4)` — the root's first entry a volume label


def single_sided_records(disk, first, count):
    """`count` records from `first` of a single-sided disk, off the medium's first side (`Floppy._records_at`'s map)."""
    track_sectors = st_build.SECTORS_PER_TRACK
    return b"".join(disk[((each // track_sectors) * st_build.HEADS * track_sectors + each % track_sectors) * SECTOR:][:SECTOR]
                    for each in range(first, first + count))


def test_the_disk_formatted_single_sided_is_a_new_boot_sector_two_empty_fats_an_empty_root_and_virgin_data():
    """THE FORMAT'S DISK, read back through the BPB its new boot sector gives: the two FATs alike — the media word, then
    nothing allocated —, the root empty but its first entry (the volume label's attribute), every data record the
    virgin word over; and the medium's second side, which a single-sided format never touches, the disk's as it was."""
    disk, before = desk.walked(desk.FORMATTED).machine.boot.disk, aes_boot.inf_disk_of()
    _sector_bytes, cluster_records, _cluster_bytes, root_records, fat_records, second_fat, data, clusters, _flags = (
        aes_boot.BPB_WORDS.unpack(aes_boot.bpb_of(disk)))
    first_fat, other_fat = (single_sided_records(disk, at, fat_records) for at in (second_fat - fat_records, second_fat))
    assert first_fat == other_fat == FAT_HEAD + bytes(fat_records * SECTOR - len(FAT_HEAD))
    root = single_sided_records(disk, second_fat + fat_records, root_records)
    assert root[VOLUME_LABEL_ATTRIBUTE_AT] == st_build.ATTR_VOLUME_LABEL and not any(root[st_build.DIR_ENTRY_BYTES:])
    assert single_sided_records(disk, data, clusters * cluster_records) == aes_boot.virgin_sector(0xe5e5) * (clusters * cluster_records)
    side_1 = [((track * st_build.HEADS + 1) * st_build.SECTORS_PER_TRACK * SECTOR) for track in range(st_build.TRACKS)]
    track_bytes = st_build.SECTORS_PER_TRACK * SECTOR
    assert all(disk[at:at + track_bytes] == before[at:at + track_bytes] for at in side_1)


# ---- GETBPB AND RWABS: the model's, held to the ROM's own over the model's Floprd ----------------------------------------------------
@pytest.mark.parametrize("which", ("drive B:'s first log-in, a blank disk", "drive B:'s first log-in, a disk formatted single-sided",
                                   "drive A:'s own disk, read again"))
def test_a_served_getbpb_stores_what_the_rom_s_own_getbpb_stores_over_the_served_floprd(which):
    """THE ROM'S GETBPB RUN IN PLACE — its Floprd of the boot sector the model's — and the model's Getbpb served at
    the entry, over the same machine: the same answer, and the same megabyte outside the routine's own stack (the
    drive's record, BPB, geometry and serial; the driver's boot-sector buffer; the mode; the write-protect copy)."""
    device, in_b = {"drive B:'s first log-in, a blank disk": (B, aes_boot.blank_disk()),
                    "drive B:'s first log-in, a disk formatted single-sided": (B, desk.walked(desk.FORMATTED).machine.boot.disk),
                    "drive A:'s own disk, read again": (A, None)}[which]
    ours, theirs = inf_memory(), inf_memory()
    answers = [run(memory, aes_boot.Floppy(memory, aes_boot.inf_disk_of(), in_b), aes_boot.GETBPB, struct.pack(">H", device))
               for run, memory in ((served, ours), (rom_s_own, theirs))]
    assert answers[0] == answers[1] == aes_boot.driver_record(ours) + device * aes_boot.FLOPPY_BPB_RECORD_BYTES
    assert outside_the_stack(ours) == outside_the_stack(theirs)
    if device == B:
        assert bytes(ours[answers[0]:answers[0] + aes_boot.FLOPPY_RECORD_FLAGS]) == aes_boot.bpb_of(in_b)[:aes_boot.FLOPPY_RECORD_FLAGS]


def formatted_memory():
    """The machine File > Format left (`aes_desk.FORMATTED`: drive A: logged in single-sided), its battery's RAM free."""
    machine = desk.walked(desk.FORMATTED).machine
    return inf_memory(machine.ram), machine.boot.disk


@pytest.mark.parametrize("record, count", ((0, 1), (8, 3), (17, 9), (700, 20)))
def test_rwabs_maps_a_single_sided_disk_s_records_as_the_rom_s_own_rwabs_does(record, count):
    """A SINGLE-SIDED DISK lies on the medium's first side: the ROM's Rwabs maps a record through the drive's record
    (its sectors a cylinder and a track), and the model's — the reads across a track's end and past the first side's
    half — land the same bytes, and nothing else, as the ROM's own Rwabs over the model's Floprd."""
    ours, disk = formatted_memory()
    theirs = bytearray(ours)
    frame = struct.pack(">HIHHH", 0, BUFFER, count, record, A)
    answers = [run(memory, aes_boot.Floppy(memory, disk), aes_boot.RWABS, frame) for run, memory in ((served, ours), (rom_s_own, theirs))]
    assert answers == [0, 0] and outside_the_stack(ours) == outside_the_stack(theirs)
    track_sectors = st_build.SECTORS_PER_TRACK                      # (one side: a cylinder is a track)
    on_side_0 = (disk[((each // track_sectors) * st_build.HEADS * track_sectors + each % track_sectors) * SECTOR:][:SECTOR]
                 for each in range(record, record + count))
    assert bytes(ours[BUFFER:BUFFER + count * SECTOR]) == b"".join(on_side_0)


def test_a_changed_drive_s_rwabs_answers_e_chng_unless_its_flag_asks_no_media_check():
    """`$fc12f8`: `cmpi.w #2,8(a6); bge` — a flag of 2 or more transfers whatever the drive's mode (the format's FAT
    and root, flag 3); a lower one, the drive held CHANGED, answers E_CHNG and moves nothing — a read (flag 0: GEMDOS's
    first after the format) or a WRITE (flag 1: nothing reaches the disk) —, the mode left."""
    assert rom_words(aes_boot.RWABS_NO_MEDIA_CHECK_AT, 4) == (0x0c6e, aes_boot.RWABS_NO_MEDIA_CHECK, 0x0008, 0x6c1c)
    memory, disk = inf_memory(), aes_boot.inf_disk_of()
    floppy = aes_boot.Floppy(memory, disk)
    memory[aes_boot.driver_mode(memory)] = aes_boot.MEDIA_CHANGED
    assert served(memory, floppy, aes_boot.RWABS, struct.pack(">HIHHH", 0, BUFFER, 1, 3, A)) == addrs.E_CHNG_LONG
    assert not any(memory[BUFFER:BUFFER + SECTOR]) and floppy.changed()
    memory[BUFFER:BUFFER + SECTOR] = bytes((0xa5,)) * SECTOR
    assert served(memory, floppy, aes_boot.RWABS, struct.pack(">HIHHH", 1, BUFFER, 1, 3, A)) == addrs.E_CHNG_LONG
    assert floppy.disk == disk and floppy.changed()
    memory[BUFFER:BUFFER + SECTOR] = bytes((0x5a,)) * SECTOR
    assert served(memory, floppy, aes_boot.RWABS, struct.pack(">HIHHH", 3, BUFFER, 1, 3, A)) == 0
    assert floppy.disk[3 * SECTOR:4 * SECTOR] == bytes((0x5a,)) * SECTOR and floppy.changed()


# ---- DRIVE B: the ROM's own two-drive path -------------------------------------------------------------------------------------------
SYSVAR_NFLOPS = 0x4a6                   # word: how many floppy drives the BIOS counts (`$fc1ebe` compares it with 1)
ONE_DRIVE_SWAP = 0xfc1ebe


def test_drive_b_is_the_rom_s_two_drive_path_and_a_disk_is_put_there_only_where_none_was_logged_in():
    """EVERY CAPTURE COUNTS TWO FLOPPIES, so the driver's one-drive swap (`$fc1ebe`: `cmpi.w #1,_nflops` — the
    "insert disk B" critical error) is not taken and drive 1 is a second drive. A disk is put in drive B: of a machine
    whose drive B: was never logged in (its record all zeros, as every capture's) — once; a machine without one
    refuses drive 1 by name."""
    assert rom_words(ONE_DRIVE_SWAP, 4) == (0x0c79, 0x0001, 0x0000, SYSVAR_NFLOPS)
    for capture in (aes_boot.preinit, aes_boot.accessory_preinit, aes_boot.inf_preinit, aes_boot.files_preinit):
        assert case.word_in(capture().ram, SYSVAR_NFLOPS) == 2
    with_b = desk.MACHINES[desk.DISK_IN_B]()
    assert with_b.boot.drive_b == aes_boot.blank_disk() and with_b.ram == aes_boot.inf_machine().ram
    with pytest.raises(Refused, match="holds one already, or was logged in"):
        aes_boot.with_a_disk_in_drive_b(with_b, aes_boot.blank_disk())
    copied = desk.walked(desk.COPIED).machine
    with pytest.raises(Refused, match="holds one already, or was logged in"):
        aes_boot.with_a_disk_in_drive_b(aes_boot.Machine(copied.boot._replace(drive_b=None)), aes_boot.blank_disk())
    memory = inf_memory()
    with pytest.raises(Refused, match="Getbpb of drive 1: the model holds drive A: alone"):
        served(memory, aes_boot.Floppy(memory, aes_boot.inf_disk_of()), aes_boot.GETBPB, struct.pack(">H", B))


def test_drive_b_s_record_must_be_its_disk_s_once_logged_in_unless_the_driver_holds_it_changed():
    copied = desk.walked(desk.COPIED).machine
    memory = copied.image()
    aes_boot.Floppy(memory, copied.boot.disk, copied.boot.drive_b)       # (held CHANGED: the copy wrote its boot sector)
    assert memory[aes_boot.driver_mode(memory) + B] == aes_boot.MEDIA_CHANGED
    memory[aes_boot.driver_mode(memory) + B] = aes_boot.MEDIA_UNCHANGED
    with pytest.raises(Refused, match="drive B:'s record .* is not the disk in it"):
        aes_boot.Floppy(memory, copied.boot.disk, copied.boot.drive_b)


# ---- THE PRINTER ---------------------------------------------------------------------------------------------------------------------
HOLD_OFF_AT = 0xfc209a                  # the driver's hold-off: `_hz_200 - PRINTER_RETRY_AT`, `cmpi.l #1000`, `bcs` not ready


def test_the_printer_s_send_is_the_driver_s_port_transaction_and_its_busy_line_a_ready_printer_s():
    """THE PORT TRANSACTION the model answers begins where the ROM's driver has seen BUSY clear (`move.w sr,d3; ori.w
    #$700,sr`), reads the character where the driver does, and answers what the driver answers (sent); the GPIP a
    machine with a printer on line is served has BUSY clear and nothing else."""
    assert rom_words(aes_boot.PRINTER_SEND, 3) == (0x40c3, 0x007c, 0x0700)
    assert rom_words(0xfc20e4, 2) == (0x302f, aes_boot.PRINTER_CHARACTER_AT)
    assert rom_words(0xfc20f4, 2) == (0x70ff, 0x4e75) and addrs.PRINTER_SENT == aes.LONG_MASK
    gpip = aes_boot.THE_PRINTER_S_PORT["hw_seed"][addrs.MFP_GPIP]
    assert gpip == aes.BYTE_MASK ^ (1 << addrs.MFP_GPIP_PRINTER_BUSY_BIT) and set(aes_boot.THE_PRINTER_S_PORT) == {"hw_seed"}


def test_the_printer_is_not_ready_for_five_seconds_after_power_on_because_its_last_timeout_is_held_at_zero():
    """WHY THE ORACLE'S CPRNOUT ANSWERED "NOT READY": the driver's hold-off — a port that timed out less than five
    seconds ago is not tried — reads `_hz_200 - PRINTER_RETRY_AT`, and the long is 0 from power-on: on a machine up
    less than 1,000 ticks (the capture's, 563: no time passes in the model) the driver answers 0 WITHOUT POLLING THE
    PORT (no GPIP read) and stamps the time, so the alert's Retry fails again until five more seconds have passed."""
    assert rom_words(HOLD_OFF_AT, 8) == (0x242d, addrs.SYSVAR_HZ_200, 0x94ad, addrs.PRINTER_RETRY_AT, 0x0c82, 0x0000,
                                         addrs.PRINTER_RETRY_HOLDOFF_TICKS, 0x6518)
    alert = desk.walked("file: File > Open (the Show / Print / Cancel alert)").machine
    assert alert.long(addrs.PRINTER_RETRY_AT) == 0 and alert.long(addrs.SYSVAR_HZ_200) < addrs.PRINTER_RETRY_HOLDOFF_TICKS
    not_ready = desk.walked(desk.NOT_READY)
    assert not_ready.steps[-1].boot.hardware_reads == () and not_ready.machine.long(addrs.PRINTER_RETRY_AT) > 0
    again = desk.walked("file: the printer not ready, Retry (not ready again)").steps[-1].boot
    assert again.hardware_reads == () and not again.printed


ENGINE_CR_AT, ENGINE_LF_AT = 0xfed6b4, 0xfed6bc      # the engine's two last bytes, in `$fed632`'s print loop (read)
MOVE_W_TO_D5 = 0x3a3c                   # move.w #<word>,d5


def test_a_file_printed_is_its_bytes_each_a_poll_of_busy_and_the_engine_s_cr_lf():
    """THE LEDGER: the file's own bytes in order, then the engine's CR LF (`move.w #13,d5`, `move.w #10,d5`) — one
    GPIP read (BUSY clear) for each byte handed."""
    assert rom_words(ENGINE_CR_AT, 2) == (MOVE_W_TO_D5, addrs.CON_CR) and rom_words(ENGINE_LF_AT, 2) == (MOVE_W_TO_D5, addrs.CON_LF)
    boot = desk.walked("file: File > Open, five seconds, Print clicked (printed)").steps[-1].boot
    assert boot.printed == aes_boot.default_inf() + b"\r\n"
    assert boot.hardware_reads == ((addrs.MFP_GPIP, aes_boot.THE_PRINTER_S_PORT["hw_seed"][addrs.MFP_GPIP]),) * len(boot.printed)


PRINTER_DRIVER = 0xfc2090               # the BIOS's Bconout of the parallel port: `$fc209a` its hold-off
PRINTER_PORT = 0                        # Bconout's device: the parallel port
A_BYTE_PAST_ASCII = 0xc4                # (DESKTOP.INF, the one file printed, is ASCII: no chain hands one)
UP_FOR = 0x10000                        # the ticks the machine has been up in the driver's runs below (any past the hold-off)
NOP = 0x4e71                            # at the driver's return: a served stop's answer lands there, and the run ends past it


def the_printer_driver_run(since_the_timeout, printer):
    """THE ROM'S OWN PRINTER DRIVER run in place for one byte — `Bconout(PRINTER_PORT, A_BYTE_PAST_ASCII)`'s frame,
    `since_the_timeout` ticks after the port last timed out (`_hz_200 - PRINTER_RETRY_AT`) — on the DESKTOP.INF machine
    with a printer on line, or none; the kit's vet of the run made: `(D0, its GPIP reads, the bytes printed)`."""
    memory = inf_memory()
    memory[addrs.SYSVAR_HZ_200:addrs.SYSVAR_HZ_200 + LONG_BYTES] = struct.pack(">I", UP_FOR)
    memory[addrs.PRINTER_RETRY_AT:addrs.PRINTER_RETRY_AT + LONG_BYTES] = struct.pack(">I", UP_FOR - since_the_timeout)
    framed(memory, struct.pack(">HH", PRINTER_PORT, A_BYTE_PAST_ASCII))
    memory[RETURNED_TO:RETURNED_TO + WORD_BYTES] = struct.pack(">H", NOP)
    registers = {**aes_boot.inf_preinit().registers, "pc": PRINTER_DRIVER, "sr": SUPERVISOR_MASKED, "a7": STACK,
                 "isp": STACK, "a5": 0}
    run = aes_boot._Run(memory, aes_boot.Floppy(memory, aes_boot.inf_disk_of()), ROM_RUN_INSNS,
                        until=RETURNED_TO + WORD_BYTES, printer=printer)
    try:
        run.to_an_idle(registers, {})
        answer, reads = aes_boot._register("d0"), tuple(emu.hw_events())
    finally:
        aes_boot._CPU.m68k_set_irq(aes_boot.NO_INTERRUPT)
        emu.bench_abort()
    aes_boot.rom_bench.vet_the_run_just_made("the ROM's printer driver")
    return answer, reads, bytes(run.printed)


def test_the_hold_off_is_a_thousand_ticks_exactly_and_a_byte_past_ascii_is_printed_whole():
    """THE ROM'S OWN DRIVER, a printer on line: 999 ticks after the port's last timeout it answers 0 (not ready) and
    reads no GPIP; at 1,000 it polls BUSY once, finds it clear, and hands the port the byte — the model's ledger holds
    it WHOLE, its top bit too — answering sent."""
    assert the_printer_driver_run(addrs.PRINTER_RETRY_HOLDOFF_TICKS - 1, printer=True) == (0, (), b"")
    gpip = aes_boot.THE_PRINTER_S_PORT["hw_seed"][addrs.MFP_GPIP]
    assert the_printer_driver_run(addrs.PRINTER_RETRY_HOLDOFF_TICKS, printer=True) == (
        addrs.PRINTER_SENT, ((addrs.MFP_GPIP, gpip),), bytes((A_BYTE_PAST_ASCII,)))


def test_a_machine_with_no_printer_on_line_is_refused_its_gpip_read_by_name():
    """THE PRINTER IS A MACHINE'S, NOT EVERY RUN'S: with none on line the GPIP is declared by nothing, and a run that
    reads it — the printer driver's poll here; the RS232 handshake or the monitor detect elsewhere — is REFUSED BY
    NAME by the kit, as before band 6 wave 4."""
    with pytest.raises(AssertionError, match=f"read modelled hardware byte.s. nothing declared .{addrs.MFP_GPIP:#x}"):
        the_printer_driver_run(addrs.PRINTER_RETRY_HOLDOFF_TICKS, printer=False)


def test_a_gpip_read_that_is_no_busy_poll_of_the_printer_s_is_refused_by_name():
    """ON A MACHINE WITH A PRINTER, EVERY GPIP READ MUST BE THE DRIVER'S BUSY POLL BEFORE A BYTE (one a byte): the
    ROM reads the same byte at its RS232 handshake (`$fc21c2`), its monitor detect (`$fc070a`) and the FDC's done line
    — a read with no byte handed, or a byte with no read, is refused by name, never labelled the printer's."""
    floppy = aes_boot.Floppy(inf_memory(), aes_boot.inf_disk_of())
    poll = (addrs.MFP_GPIP, aes_boot.THE_PRINTER_S_PORT["hw_seed"][addrs.MFP_GPIP])
    assert aes_boot.devices_answered(floppy, (poll,) * 2, b"AB") == (aes_boot.THE_PRINTER,)
    assert aes_boot.devices_answered(floppy, (), b"") == ()
    for reads, printed in (((poll,), b""), ((poll,) * 2, b"A"), ((), b"A")):
        with pytest.raises(Refused, match="a GPIP read that is no BUSY poll of the printer's is served by no device here"):
            aes_boot.devices_answered(floppy, reads, printed)


PRINT_CHAINS = ("file: File > Open, five seconds, Print clicked (printed)", desk.NOT_READY,
                "file: the printer not ready, Cancel", "file: the printer not ready, Retry (not ready again)",
                "file: the printer not ready, five seconds, Retry (printed)")


def test_the_printer_is_on_line_on_the_print_chains_machines_alone():
    """THE PRINT CHAINS GO ON FROM THE ALERT'S MACHINE WITH A PRINTER PUT ON LINE (`aes_desk.PRINTER_ON_LINE`): the
    same megabyte as the alert's, `Boot.printer` set — and theirs alone of the block's; a second printer is refused."""
    alert = desk.walked(desk.SHOW_PRINT_ALERT).machine
    on_line = desk.MACHINES[desk.PRINTER_ON_LINE]()
    assert not alert.boot.printer and on_line.boot.printer and on_line.ram == alert.ram
    with pytest.raises(Refused, match="has one already"):
        aes_boot.with_a_printer_on_line(on_line)
    assert {name for name in SLICE_H if desk.walked(name).machine.boot.printer} == set(PRINT_CHAINS)


def test_five_seconds_are_the_hold_off_s_thousand_ticks_to_the_tick():
    """FIVE SECONDS (`aes_desk.FIVE_SECONDS`) is the hold-off and not a tick more: after the step alone — no click,
    whose own ticks would carry a short wait past the bound — the machine stands exactly 1,000 ticks past the
    timeout the "not ready" stamped, where the driver (above) prints and at 999 does not."""
    machine = aes_boot.Machine(desk.walked("file: the printer not ready, five seconds, Retry (printed)").steps[0].boot)
    assert machine.long(addrs.SYSVAR_HZ_200) - machine.long(addrs.PRINTER_RETRY_AT) == addrs.PRINTER_RETRY_HOLDOFF_TICKS


# ---- THE LABELS, chain by chain -------------------------------------------------------------------------------------------------------
LABELLED = {desk.FORMATTED: {aes_boot.THE_FORMATTER}, desk.COPIED: {aes_boot.DRIVE_B, aes_boot.THE_FORMATTER},
            "file: File > Open, five seconds, Print clicked (printed)": {aes_boot.THE_PRINTER},
            "file: the printer not ready, five seconds, Retry (printed)": {aes_boot.THE_PRINTER},
            desk.NOT_THE_SAME_TYPE: {aes_boot.DRIVE_B}}     # (band 6 wave 4's G2 chain: its id is a key, held below)
SLICE_H_S_LAST = "file: File > Open, five seconds, Print clicked (printed)"
SLICE_H = tuple(desk.CHAINS)[tuple(desk.CHAINS).index(desk.FORMAT_UP):tuple(desk.CHAINS).index(SLICE_H_S_LAST) + 1]


def test_a_later_wave_s_device_chain_names_its_classes_too():
    """SLICE H's PIN BOUNDED TO ITS OWN CHAINS: a later wave's chain on a device machine is held by the same label table
    (band 6 wave 4's G2: a single-sided disk in drive B:, the copy refused — drive B: answered it)."""
    name = desk.NOT_THE_SAME_TYPE
    assert name not in SLICE_H
    assert set().union(*(step.boot.devices for step in desk.walked(name).steps)) == LABELLED[name]


@pytest.mark.parametrize("name", SLICE_H)
def test_each_chain_names_the_classes_of_the_devices_that_answered_it_and_no_other(name):
    """EACH DEVICE IS LABELLED WHERE IT ANSWERED, never silently: the union of the chain's steps' `devices` is the
    formatter's for the format, drive B:'s and the formatter's for the copy, the printer's where a byte was printed —
    and nothing for the chains that only bring a dialog up, leave it, or meet the printer's hold-off."""
    assert set().union(*(step.boot.devices for step in desk.walked(name).steps)) == LABELLED.get(name, set())


def test_the_copy_s_buffer_is_all_of_free_memory_and_clears_the_desk_s_userdef_stack():
    """THE COPY IS A BUILT-IN RUN AFTER deskmain's RETURN (the shell's), with the desk's blocks freed: its buffer is
    all of free memory but a kilobyte (`dos_avail` - 1,024), and its tracks fill the kilobyte that was the userdef
    stack — stored whole, as a launch's clear stores it."""
    assert desk.depths(desk.COPIED)[desk.USERDEF_STACK] == desk.USERDEF_STACK_BYTES
    assert desk.COPIED in desk.THE_DESK_S_BLOCKS_ARE_CLEARED_IN


# ---- THE HARNESS GAP: a box of an object of a sub-tree ---------------------------------------------------------------------------------
COPY_DIALOG_ROOT, COPY_BUTTON, COPY_BUTTON_IN_THE_TREE = 11, 5, 16


def test_an_object_of_a_dialog_laid_inside_another_s_tree_is_boxed_from_its_own_root_and_refused_from_the_outer_one():
    """THE DISKCOPY DIALOG is the utility tree's objects 11..16, a tree of its own rooted at 11: its COPY is that
    root's object 5 — found so by `dialog_button` — and boxing it as object 16 of the outer tree, which once climbed
    for ever, is refused by name."""
    machine = desk.walked(desk.COPY_UP).machine
    tree = case.long_in(machine.ram, UTILITY_TREE) & BUS
    assert desk.dialog_button(machine, "COPY") == (tree + COPY_DIALOG_ROOT * aes.OB_BYTES, COPY_BUTTON)
    with pytest.raises(Refused, match="object 16 of the tree .* not linked under the tree's root"):
        desk.box(machine.ram, tree, COPY_BUTTON_IN_THE_TREE)
    # (refused AT NIL — past the outer root, whose tail is 10: no object below the tree is read)
    with pytest.raises(aes_objects.Unrooted, match="reaches NIL past object 0"):
        aes_objects.parent_by_climbing(tree, COPY_BUTTON_IN_THE_TREE, machine.ram)
    x, y, width, height = desk.box(machine.ram, tree + COPY_DIALOG_ROOT * aes.OB_BYTES, COPY_BUTTON)
    assert (width, height) == tuple(aes_objects.object_word(machine.ram, tree, COPY_BUTTON_IN_THE_TREE, field) for field in desk.SIZE_FIELDS)
    assert (x + width // 2, y + height // 2) == desk.button_point(machine, "COPY")


UTILITY_TREE = aes_deskbind.DESK_GLOBALS["AES_DESK_UTIL_TREE"]   # the utilities' tree, as `$fed888` fetches it
