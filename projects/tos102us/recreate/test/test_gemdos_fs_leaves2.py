"""`Fdatime` ($57, `src/gemdos/fs_file.c`), `Dfree` ($36) and `Dgetpath` ($47, `src/gemdos/fs_leaves.c`)
— each entered at its own address and then THROUGH THE DISPATCHER, against the ROM's own leaf.

    $fc772e  Fdatime   the entry's two words read (and turned into the 68000's order) or turned into
                       the disk's order and written — the caller's buffer left swapped — then the
                       directory closed with flag 2; NO check of the OFD the handle names
    $fc7a68  Dfree     clusters 2..m_numcl-1 counted free by `$fc6038`, four sign-extended words out
    $fc6c1a  Dgetpath  `$fc6bd2`'s unterminated "\\A\\B\\", its last `\\` overwritten by the NUL

`Dfree` and `Dgetpath` share a prologue: a drive argument of 0 is the running process's current
drive, n is drive n-1, and `$fc67de` logs it in.
"""
import struct

import pytest

from harness import BASE_IMAGE, addrs, emu, make_image

import case
import fs_file as ff
import fs_io as io
import fs_records as records
import gemdos
import gemdos_fs as fs
import gemdos_process as process

FILE = "SHORT"
FILE_OFD = io.OFD_AT
STAMP_AT = fs.USER_AT
NEW_STAMP = ff.stamp(ff.NEW_TIME, ff.NEW_DATE)
FDATIME, DFREE, DGETPATH = fs.FDATIME, fs.DFREE, fs.DGETPATH
GET, SET = 0, 1


def _leaf(leaf, values, pokes, buffers=ff.WORKING_CACHE):
    """One leaf at its own address — over `fs_file`'s cache with work in it unless the case says
    otherwise (a FAT scan must not read a made-up FAT sector)."""
    return io.run(leaf.entry, fs.leaf_glue(leaf, values), fs.leaf_pokes(leaf, values, pokes), buffers=buffers)


# ================================================================================================
# Fdatime
# ================================================================================================

OPEN = {**ff.open_entry(FILE, FILE_OFD), **ff.handle_naming(FILE_OFD)}


def _fdatime(set_flag, stamp=b"", handle=ff.A_HANDLE, pokes=OPEN):
    return _leaf(FDATIME, (STAMP_AT, handle, set_flag), {**fs.user_buffer(stamp), **pokes})


@pytest.mark.parametrize("handle,pokes,why", (
    (ff.A_HANDLE, OPEN, "a handle record"),
    (1, {**OPEN, **gemdos.standard_handles_poke([0, ff.A_HANDLE])}, "a standard handle naming it"),
))
def test_fdatime_reads_the_entry_s_time_and_date(handle, pokes, why):
    """The two words turned into the 68000's order in the caller's buffer; D0 is what the second
    swap left — the transfer's count (4) with its low word the DATE. No flush: the cache keeps its
    dirty buffers."""
    result = _fdatime(GET, handle=handle, pokes=pokes)
    assert result.after(STAMP_AT, ff.TIME_DATE_BYTES) == ff.stamp(fs.STAGED_DIRENT_TIME, fs.STAGED_DIRENT_DATE), why
    assert result.info["ret"] == fs.STAGED_DIRENT_DATE, why
    ff.assert_nothing_flushed(result)


def test_fdatime_with_a_null_buffer_answers_the_cache_pointer_s_high_half():
    """A buffer of 0 is how the directory layer asks the transfer for a POINTER into the cache
    (`$fc5e9c`), and `Fdatime` passes the caller's straight through: the read moves nothing and
    answers that pointer, the swaps turn the two words at address 0 round, and D0 is the POINTER's
    high half under the swapped word at 2 — which is what shows D0 is what the swap left of the
    read's answer, not a word of its own."""
    result = _leaf(FDATIME, (0, ff.A_HANDLE, GET), OPEN)
    assert result.info["ret"] >> 16 == fs.buffer_at(0) >> 16
    assert result.info["ret"] & fs.D0_LOW_WORD == fs.byte_swapped(case.word_in(BASE_IMAGE, 2), "H")


def test_fdatime_writes_the_entry_and_leaves_the_caller_s_buffer_swapped():
    result = _fdatime(SET, NEW_STAMP)
    entry = ff.root_entry_after(result, FILE)
    assert entry[fs.DIRENT_TIME:fs.DIRENT_STRTCL] == ff.stamp_on_disk(ff.NEW_TIME, ff.NEW_DATE)
    assert result.after(STAMP_AT, ff.TIME_DATE_BYTES) == ff.stamp_on_disk(ff.NEW_TIME, ff.NEW_DATE), \
        "the buffer was not left swapped"
    assert result.info["ret"] == 0
    ff.assert_every_buffer_flushed(result)


# THE NULL OFD, which the reconstruction does not follow (`src/gemdos/fs_file.c` halts): a handle
# naming nothing makes `$fc51c0` answer 0, and the ROM reads its "directory OFD" and "entry position"
# out of exception vectors 6 and 7 — `$06fc0b50` and `$07fc0b50` in the captured machine, the vector
# number in the top byte over the ROM's catch-all. What happens next is an ORACLE claim.
def _oracle_fdatime(set_flag, max_insns):
    pokes = fs.machine(io.engine({**process.descriptor_poke(ff.A_HANDLE, 0, ff.P_RUN),
                                  **fs.user_buffer(NEW_STAMP),
                                  **case.args(FDATIME.frame, STAMP_AT, ff.A_HANDLE, set_flag)}))
    return emu.run(make_image(pokes), addrs.GEMDOS_FDATIME, {"a5": 0}, max_insns=max_insns)


def test_the_rom_s_fdatime_get_on_a_null_ofd_only_swaps_the_caller_s_buffer():
    """The GET arm returns: the seek is ERANGE (the "length" at `$fc0b5c` is negative), the read
    clamps to nothing, and the two swaps turn the CALLER's words round — D0 the swapped second word
    over the read's 0. No disk access, no store outside the buffer and the stack."""
    _final, writes, regs = _oracle_fdatime(GET, max_insns=10_000)
    assert regs["d0"] == fs.as_stored(ff.NEW_DATE)
    stored = {address for address in writes if not emu.STACK_GUARD_LO <= address < emu.STACK_TOP}
    assert stored == set(range(STAMP_AT, STAMP_AT + ff.TIME_DATE_BYTES))
    assert bytes(writes[STAMP_AT + index] for index in range(ff.TIME_DATE_BYTES)) == \
        ff.stamp_on_disk(ff.NEW_TIME, ff.NEW_DATE)


def test_the_rom_s_fdatime_set_on_a_null_ofd_never_returns():
    """...and the SET arm does not come back: an unclamped write through a "directory OFD" made of ROM
    code bytes. Not reconstructed, and the case says so rather than guessing."""
    with pytest.raises(RuntimeError, match="did not reach rts"):
        _oracle_fdatime(SET, max_insns=200_000)


# ================================================================================================
# Dfree
# ================================================================================================

INFO_AT = fs.USER_AT
# A directory node the snapshot leaves unused — its slot and its reference count both 0 — for a
# case's own current directory.
NODE = next(node for node in range(1, addrs.GEMDOS_DIRECTORY_NODE_COUNT)
            if case.long_in(BASE_IMAGE, fs.node_slot(node)) == 0
            and BASE_IMAGE[addrs.GEMDOS_CURDIR_REFCOUNTS + node] == 0)
DRIVE_A = 1                                 # the argument: drive n+1
CURRENT = 0
# Drive A:, logged in by the snapshot, with its table slot pointed at the STAGED DMD.
STAGED_A = fs.dmd_pointer_poke(io.DRIVE)
BASE_FREE = sum(1 for cluster in range(fs.FIRST_DATA_CLUSTER, fs.DATA_CLUSTERS)
                if fs.BASE_FAT[cluster] == 0)


def _dfree(drive, pokes=None):
    """...over the EMPTY cache, not `fs_file`'s: that one holds a made-up FAT sector a scan would read."""
    return _leaf(DFREE, (INFO_AT, drive), {**STAGED_A, **(pokes or {})}, buffers=None)


def _info(result):
    return struct.unpack(">4i", result.after(INFO_AT, fs.DISKINFO_BYTES))


def test_dfree_on_the_staged_disk():
    """Clusters 2..31 scanned, the five the files use not free; the total is `m_numcl` (32) — the
    two it never scans included."""
    result = _dfree(DRIVE_A)
    assert result.info["ret"] == 0
    assert _info(result) == (BASE_FREE, fs.DATA_CLUSTERS, fs.SECTOR_BYTES, fs.SECTORS_PER_CLUSTER)


def test_dfree_never_counts_the_last_two_clusters():
    """A partly-full disk: two more files, one ending on the LAST SCANNED cluster (31) — and the two
    clusters past the scan (32, 33) FREE, which a scan reaching either would count."""
    used = {7: 8, 8: fs.FAT12_END_OF_CHAIN, 20: fs.FAT12_END_OF_CHAIN,
            fs.DATA_CLUSTERS - 1: fs.FAT12_END_OF_CHAIN}
    past_the_scan = {fs.DATA_CLUSTERS: 0, fs.DATA_CLUSTERS + 1: 0}
    result = _dfree(DRIVE_A, fs.disk(fat={**used, **past_the_scan}))
    assert _info(result)[0] == BASE_FREE - len(used)


# B:, logged in for the case: its bit in the mask, the staged DMD in its slot, and a live directory —
# the CURRENT drive of the current-drive cases, so a leaf that took A: (drive 0) instead is told apart.
DRIVE_B = io.DRIVE + 1


def _b_logged_in(directory=fs.ROOT_DND_AT):
    mask = case.word_in(BASE_IMAGE, addrs.GEMDOS_DRIVES_OPENED) | 1 << DRIVE_B
    return {addrs.GEMDOS_DRIVES_OPENED: struct.pack(">H", mask), **fs.dmd_pointer_poke(DRIVE_B),
            **fs.current_directory_poke(DRIVE_B, NODE, directory), **gemdos.current_drive_poke(DRIVE_B)}


def test_dfree_counts_from_cluster_2():
    """The scan's first cluster is the data area's first: a disk whose cluster 2 is free counts it."""
    result = _dfree(DRIVE_A, fs.disk(fat={fs.SUBDIR_CLUSTER: 0}))
    assert _info(result)[0] == BASE_FREE + 1


def test_dfree_of_the_current_drive_reads_the_basepage():
    """Argument 0: the drive is `p_run`'s current one, B: here — whose table slot names the staged
    DMD, where A:'s names the snapshot's own."""
    result = _dfree(CURRENT, {**_b_logged_in(), **fs.dmd_pointer_poke(io.DRIVE, 0)})
    assert result.info["ret"] == 0
    assert _info(result)[0] == BASE_FREE


FAT16_END_OF_CHAIN = 0xFFFF
# A USED FAT16 entry whose low byte is 0, on a cluster the base disk leaves free: a scan that tested
# only the byte would count it.
FAT16_HIGH_BYTE_ONLY = 0x8000
HIGH_BYTE_ONLY_CLUSTER = 9


def test_dfree_on_a_fat16_drive():
    entries = {cluster: value for cluster, value in fs.BASE_FAT.items() if cluster >= fs.FIRST_DATA_CLUSTER}
    entries[fs.SPAN_CLUSTER + 2] = FAT16_END_OF_CHAIN
    entries[HIGH_BYTE_ONLY_CLUSTER] = FAT16_HIGH_BYTE_ONLY
    result = _dfree(DRIVE_A, {**io.drive(fat16=1), **io.fat16_disk(entries)})
    assert _info(result)[0] == BASE_FREE - 1


def test_dfree_logs_a_new_drive_in_and_scans_the_fat_it_built():
    """B: not logged in: `$fc67de` asks the staged `Getbpb`, builds a DMD out of the pool — whose FAT
    pseudo-file then reads the staged disk's FAT through the cache — and the count is the same."""
    result = _dfree(DRIVE_A + 1)
    assert result.info["ret"] == 0
    assert _info(result) == (BASE_FREE, fs.DATA_CLUSTERS, fs.SECTOR_BYTES, fs.SECTORS_PER_CLUSTER)


def test_dfree_answers_minus_1_for_ENSMEM_too():
    """A log-in the pool cannot serve is ENSMEM from `$fc67de`; `Dfree` tests only the WORD's sign
    and answers its own `moveq #-1`."""
    result = _dfree(DRIVE_A + 1, records.pool_spent())
    assert result.info["ret"] == fs.GEMDOS_ERROR


def test_dfree_of_a_drive_that_will_not_open_is_minus_1():
    """B: is not logged in, and a `Getbpb` answering 0 fails the log-in: `moveq #-1`, nothing stored."""
    result = _dfree(DRIVE_A + 1, fs.getbpb_answer(0))
    assert result.info["ret"] == fs.GEMDOS_ERROR
    assert result.after(INFO_AT, fs.DISKINFO_BYTES) == bytes([fs.SLACK_FILL]) * fs.DISKINFO_BYTES


# ================================================================================================
# Dgetpath
# ================================================================================================

PATH_AT = fs.USER_AT
PATH_BYTES = 0x20
OUTER_DND = records.record_slot(4)
INNER_DND = records.record_slot(5)
TWO_LEVELS = {**fs.stage_dnd(OUTER_DND, name=fs.fcb_name("FOLDER"), parent=fs.ROOT_DND_AT),
              **fs.stage_dnd(INNER_DND, name=fs.fcb_name("INNER", "X"), parent=OUTER_DND)}


def _current_directory(dnd):
    return fs.current_directory_poke(io.DRIVE, NODE, dnd)


def _dgetpath(drive, pokes):
    return _leaf(DGETPATH, (PATH_AT, drive), pokes)


def _path(result):
    text = result.after(PATH_AT, PATH_BYTES)
    return text[:text.index(0)]


@pytest.mark.parametrize("pokes,path,why", (
    (_current_directory(fs.ROOT_DND_AT), b"", "the root: its lone `\\` overwritten"),
    ({**TWO_LEVELS, **_current_directory(INNER_DND)}, b"\\FOLDER\\INNER.X", "two levels deep"),
))
def test_dgetpath(pokes, path, why):
    result = _dgetpath(DRIVE_A, pokes)
    assert result.info["ret"] == 0, why
    assert _path(result) == path, why
    assert result.after(PATH_AT + len(path) + 1, 1) == bytes([fs.SLACK_FILL]), why


def test_dgetpath_of_the_current_drive():
    """B:'s directory, not A:'s — A: is left on the snapshot's own root."""
    result = _dgetpath(CURRENT, {**TWO_LEVELS, **_b_logged_in(INNER_DND)})
    assert _path(result) == b"\\FOLDER\\INNER.X"


def test_dgetpath_of_a_bad_drive_is_EDRIVE_and_the_empty_string():
    result = _dgetpath(DRIVE_A + 1, fs.getbpb_answer(0))
    assert result.info["ret"] == fs.GEMDOS_EDRIVE
    assert result.after(PATH_AT, 2) == bytes([0, fs.SLACK_FILL])


# ================================================================================================
# through the dispatcher
# ================================================================================================

def test_a_dispatched_fdatime_writes_the_entry():
    result = io.dispatch_slice(FDATIME, (*gemdos.long_words(STAMP_AT), ff.A_HANDLE, SET),
                               {**OPEN, **fs.user_buffer(NEW_STAMP)}, buffers=ff.WORKING_CACHE)
    assert result.info["ret"] == 0
    assert ff.root_entry_after(result, FILE)[fs.DIRENT_TIME:fs.DIRENT_STRTCL] == ff.stamp_on_disk(ff.NEW_TIME, ff.NEW_DATE)


def test_a_dispatched_dfree_counts_the_staged_disk():
    result = io.dispatch_slice(DFREE, (*gemdos.long_words(INFO_AT), DRIVE_A), STAGED_A)
    assert _info(result)[0] == BASE_FREE


def test_a_dispatched_dgetpath_prints_the_directory():
    result = io.dispatch_slice(DGETPATH, (*gemdos.long_words(PATH_AT), DRIVE_A),
                               {**TWO_LEVELS, **_current_directory(INNER_DND)}, buffers=ff.WORKING_CACHE)
    assert _path(result) == b"\\FOLDER\\INNER.X"


# ---- the registry ------------------------------------------------------------------------------------

def _register_all():
    io.register("Fdatime, read", FDATIME.entry, fs.leaf_pokes(FDATIME, (STAMP_AT, ff.A_HANDLE, GET), OPEN),
                buffers=ff.WORKING_CACHE)
    io.register("Fdatime, write", FDATIME.entry,
                fs.leaf_pokes(FDATIME, (STAMP_AT, ff.A_HANDLE, SET), {**fs.user_buffer(NEW_STAMP), **OPEN}),
                buffers=ff.WORKING_CACHE)
    io.register("Dfree, the staged disk", DFREE.entry, fs.leaf_pokes(DFREE, (INFO_AT, DRIVE_A), STAGED_A))
    io.register("Dgetpath, two levels", DGETPATH.entry,
                fs.leaf_pokes(DGETPATH, (PATH_AT, DRIVE_A), {**TWO_LEVELS, **_current_directory(INNER_DND)}),
                buffers=ff.WORKING_CACHE)


_register_all()
