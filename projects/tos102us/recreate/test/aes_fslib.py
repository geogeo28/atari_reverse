r"""THE FILE SELECTOR's MACHINES — what `src/aes/fslib.c`'s routines are proved over (`test_aes_fslib*.py`).

EVERY MACHINE IS THE ROM's OWN fs_input's. The selector's routines run on state fs_input ($fe7d90) makes before it
calls them: three GEMDOS blocks (the names, the index, the DTA — Malloc'd, their addresses in three globals), the path
and the selection in the tree's fields, the path copied to the two buffers it works in, the whole selector drawn. None
of that is in the snapshot (the three globals are 0), and none of it is poked here: the ROM's own fs_input is RUN, over
the scheduler's own running PD0 (`aes_event.machine`) and a STAGED RAM DISK (`gemdos_fs`), into REAL GEMDOS, and
STOPPED where it first enters the routine a case is about (`entered`) — or right after its first fs_newdir returned
(`listed`: a directory read, sorted, formatted and drawn). A case then starts from what that run WROTE, with the
routine's frame the ROM's own, read off its `link`ed frame. fs_input's first pass reaches no event door: it draws,
then reads its directory before it ever waits (`-44(a6)`, set at $fe7ecc, skips its first fm_do).

A pointer that frame aims into fs_input's own locals (fs_newdir's `&count`, in the stack band no differential compares)
is moved to this module's band, so what is stored through it is compared.

THE DISK (`DISK`) is `gemdos_fs`'s six-entry root — a folder, three files, a deleted entry, a volume label — plus one
folder per directory shape the selector must be right about: no name, one, nine (a full list), ten (the first scroll),
ninety-nine, a hundred and a hundred and one (the bell, and the cut at a hundred), names already in order and in
reverse order and in none, folders among files of several extensions for the wildcards, and one name held three times.

GEMDOS IS REAL on both shores (`aes_shell`'s arrangement): the ROM's glue traps into the ROM's GEMDOS; our C hands the
same frame to the reconstructed dispatcher, its handlers bound to the reconstructed leaves. NOTHING HERE POISONS, for
`gemdos_fs`'s reason (savptr, the pool's chain heads); every word a routine answers through starts STALE.
"""
import ast
import atexit
import ctypes
import functools
import hashlib
import os
import struct
import sys
from collections import namedtuple

from harness import BASE_IMAGE, addrs, emu, make_image
from recreate_kit.os_map import OS_BUS_ADDR_MASK

import abi
import aes
import aes_event
import aes_gsx as gsx
import aes_objdraw as od
import aes_shell as sh
import aes_strings
import case
import derived
import fs_io as io
import gemdos
import gemdos_console as console
import gemdos_fs as fs
import isr
import opcodes as op
import trap
import vdi
import vdi_helpers
from address_hook import bind_pointer
from case import merge_pokes

FS = aes.header_constants("fslib.h")
WORD_BYTES, LONG_BYTES = aes.WORD_BYTES, aes.LONG_BYTES
IMAGE, WORD, LONG = vdi.IMAGE_ARG, vdi.WORD_ARG, vdi.LONG_ARG

# ---- the routines, and how each is called ----------------------------------------------------------------------------
START, BACK, PSPEC, ACTIVE = "AES_ROM_FS_START", "AES_ROM_FS_BACK", "AES_ROM_FS_PSPEC", "AES_ROM_FS_ACTIVE"
ONE_SCROLL, FORMAT, SEL, NSCROLL = "AES_ROM_FS_1SCROLL", "AES_ROM_FS_FORMAT", "AES_ROM_FS_SEL", "AES_ROM_FS_NSCROLL"
NEWDIR, SNEXT, CCONOUT = "AES_ROM_FS_NEWDIR", "AES_ROM_DOS_SNEXT", "AES_ROM_DOS_CCONOUT"
INPUT = "AES_ROM_FS_INPUT"
SIGNATURES = {
    START: (None, (IMAGE,)),
    BACK: (aes.LONG_ANSWER, (IMAGE, LONG, LONG)),
    PSPEC: (aes.LONG_ANSWER, (IMAGE, LONG, LONG)),
    ACTIVE: (aes.WORD_ANSWER, (IMAGE, LONG, LONG, LONG)),
    ONE_SCROLL: (aes.WORD_ANSWER, (WORD, WORD, WORD)),
    FORMAT: (aes.WORD_ANSWER, (IMAGE, LONG, WORD, WORD)),
    SEL: (None, (IMAGE, WORD, WORD)),
    NSCROLL: (aes.WORD_ANSWER, (IMAGE, LONG, LONG, WORD, WORD, WORD, WORD)),
    NEWDIR: (None, (IMAGE, LONG, LONG, LONG, LONG, LONG)),
    SNEXT: (aes.WORD_ANSWER, (IMAGE,)),
    INPUT: (aes.WORD_ANSWER, (IMAGE, LONG, LONG, LONG)),
}
for _name, (_restype, _argtypes) in SIGNATURES.items():
    aes.declare_alcyon(_name, _restype, _argtypes)
# ...and the bell's Cconout, which goes through $fe3c28 and parks its CALLER's return address: a host argument
# (dos_free's precedent, `aes_shell`).
aes.declare_alcyon(CCONOUT, aes.LONG_ANSWER, (IMAGE, LONG, WORD), host_arguments=1)

SELECTOR = od.trees()["selector"]
ROWS = FS["FS_ROWS"]
FIRST_NAME = FS["FS_FIRST_NAME"]
UP_ARROW, DOWN_ARROW = FS["FS_UP_ARROW"], FS["FS_DOWN_ARROW"]
NAMES_KEPT = FS["FS_NAMES"]
FOLDER, FILE = bytes([FS["FS_FOLDER_MARK"]]), bytes([FS["FS_FILE_MARK"]])
TEXT, NAME = FS["AES_FS_TEXT"], FS["AES_FS_NAME"]
# The room of the two scratches: up to the next global after each (gl_mntree, sh_envrn's copy) — nothing bounds a
# string in them, and a spec longer than its room runs on over what follows.
TEXT_ROOM = aes.AES_GL_MNTREE - TEXT
NAME_ROOM = aes.AES_SH_SCRATCH - NAME

# ---- this module's band ------------------------------------------------------------------------------------------------
BAND_OFFSET = 0x3C00                    # past test_aes_fmdo.py's band (+$3a00), below test_aes_wm_update.py's (+$3f00)
BAND_BYTES = 0x200
BAND_AT = aes.SPAN.claim(aes.WINDOW_AT + BAND_OFFSET, BAND_BYTES,
                         "test/aes_fslib.py: fs_input's path and selection, answer words, an application's path")
PATH_BYTES = 0x80                       # fs_input's path, as the application hands it: room for it to grow
PATH_AT = BAND_AT
FILE_BYTES = 0x20
FILE_AT = PATH_AT + PATH_BYTES          # ...its selection
BUTTON_AT = FILE_AT + FILE_BYTES        # ...and its button word
COUNT_AT = BUTTON_AT + WORD_BYTES       # fs_active's and fs_newdir's count, moved out of fs_input's frame
ROW_AT = COUNT_AT + WORD_BYTES          # fs_nscroll's selected row, the same
ANSWER_WORDS = 3
STRING_BYTES = 0x100                    # the band's upper half:
STRING_AT = BAND_AT + BAND_BYTES - STRING_BYTES    # an application's path, for fs_back and fs_pspec alone
assert ROW_AT + WORD_BYTES <= STRING_AT
STALE_ANSWERS = {BUTTON_AT: vdi.pack_words(*[aes.STALE_WORD] * ANSWER_WORDS)}
STALE_SLOTS = merge_pokes(*(aes.stale_host_slot(role) for role in (
    "AES_FS_START_TREE", "AES_FS_FORMAT_FRAME", "AES_FS_NSCROLL_FRAME", "AES_FS_INPUT_FRAME", "AES_OB_DRAW_POSITION",
    "AES_OB_CHANGE_FRAME")))

for _global in ("AES_AD_FSTREE", "AES_AD_HGMICE", "AES_AD_FSDTA", "AES_AD_FSNAMES", "AES_AD_FSINDEX"):
    aes.declare_case_field(FS[_global], LONG_BYTES, "the file selector's globals")
aes.declare_case_field(FS["AES_GL_RFS"], aes.GRECT_BYTES, "the selector's centred box")
aes.declare_case_field(TEXT, TEXT_ROOM, "the selector's text scratch")
aes.declare_case_field(NAME, NAME_ROOM, "the selector's name scratch")

# ---- the disk ----------------------------------------------------------------------------------------------------------
# A directory's entries: (name, extension) for a plain file — or (name, extension, attribute): a folder among them (its
# SUBDIR bit set, whatever other bit is), or a file with an attribute. Folders hold nothing (their cluster is the
# disk's empty SUBDIR's: the selector never walks into one here).
def numbered(count, extension="DAT"):
    """`count` files F000.. — in the order a directory that grew a file at a time holds them."""
    return tuple((f"F{index:03d}", extension) for index in range(count))


ALPHABET = tuple((name, "TXT") for name in ("ALPHA", "BRAVO", "CHARLIE", "DELTA", "ECHO", "FOXTROT", "GOLF", "HOTEL",
                                             "INDIA", "JULIET", "KILO", "LIMA", "MIKE"))
SUBDIR_ATTR = fs.GEMDOS_ATTR_SUBDIR
# Folders among files, and the names wildcmp's arms tell apart: `*` at a name's end and before its dot, `?` for one
# character but never a dot, no extension at all, an eight-character name, a one-character one.
MIXED = (("README", "TXT"), ("TOOLS", "", SUBDIR_ATTR), ("A", "C"), ("LONGNAME", "PRG"), ("NOTES", ""),
         ("AUTO", "", SUBDIR_ATTR), ("READ", "ME"), ("AB", "TXT"), ("ABC", "TOS"), ("DATA", "DAT"), ("ZOO", "", SUBDIR_ATTR),
         ("TEST", "TXT"))
# One name three times over, as a damaged directory holds it (GEMDOS answers each entry): names the sort finds EQUAL.
TWINS = (("SAME", "TXT"), ("OTHER", "TXT"), ("SAME", "TXT"), ("SAME", "TXT"))
# Twenty-eight names in an order the shell sort's gaps do not all meet alike: one where the pairs it compares last —
# left in the two scratches — tell a sort that steps back by its gap from one that steps back a name at a time.
SHUFFLED_ORDER = (15, 1, 17, 4, 5, 27, 13, 10, 9, 19, 8, 25, 12, 20, 3, 24, 7, 16, 6, 26, 2, 23, 14, 0, 18, 11, 21, 22)
SHUFFLED = tuple((f"S{index:02d}", "DAT") for index in SHUFFLED_ORDER)
FOLDERS = {
    "ONE": (("ONLY", "TXT"),),
    "NINE": numbered(9),
    "TEN": numbered(10),
    "NINETY9": numbered(99),
    "HUNDRED": numbered(100),
    "BIG": numbered(101),
    "SORTED": ALPHABET,
    "REVERSE": tuple(reversed(ALPHABET)),
    "MIXED": MIXED,
    "TWINS": TWINS,
    "SHUFFLED": SHUFFLED,
}
EMPTY_FOLDER = "SUBDIR"                 # the base disk's own: `.` and `..` alone
ENTRIES_PER_CLUSTER = fs.CLUSTER_BYTES // fs.DIRENT_BYTES
DOT_ENTRIES = 2
FIRST_FOLDER_CLUSTER = fs.SPAN_CLUSTER + fs.SPAN_CLUSTERS       # past the base disk's last file


def _folder_clusters(files):
    return -(-(len(files) + DOT_ENTRIES) // ENTRIES_PER_CLUSTER)


def _attribute(row):
    """The attribute byte of a directory's entry `row`."""
    _name, _extension, *attribute = row
    return attribute[0] if attribute else fs.ATTR_NONE


def _entry(row, cluster=0):
    name, extension = row[:2]
    return fs.staged_dirent(name, extension, _attribute(row), fs.SUBDIR_CLUSTER if _attribute(row) & SUBDIR_ATTR else cluster)


def _disk(folders=None):
    """The base disk with `folders` (FOLDERS by default) added to its root, each a chain of consecutive clusters
    holding its entries."""
    fat, clusters, root, first = {}, {}, [fs.staged_dirent(*row) for row in fs.ROOT_FILES], FIRST_FOLDER_CLUSTER
    for folder, files in (FOLDERS if folders is None else folders).items():
        count = _folder_clusters(files)
        entries = b"".join(fs.dots(first, 0) + [_entry(row) for row in files]).ljust(count * fs.CLUSTER_BYTES, b"\0")
        for index in range(count):
            cluster = first + index
            fat[cluster] = cluster + 1 if index < count - 1 else fs.FAT12_END_OF_CHAIN
            clusters[cluster] = entries[index * fs.CLUSTER_BYTES:(index + 1) * fs.CLUSTER_BYTES]
        root.append(fs.staged_dirent(folder, "", SUBDIR_ATTR, first))
        first += count
    assert first <= fs.FAT_ENTRIES and len(root) <= fs.ROOT_ENTRIES, "the folders do not fit the staged disk"
    image = bytearray(fs.disk(fat, clusters)[fs.IMAGE_AT])
    at = fs.ROOT_RECORD * fs.SECTOR_BYTES
    image[at:at + fs.ROOT_SECTORS * fs.SECTOR_BYTES] = b"".join(root).ljust(fs.ROOT_SECTORS * fs.SECTOR_BYTES, b"\0")
    return {fs.IMAGE_AT: bytes(image)}


DISK = _disk()
ROOT_PATH = "A:\\*.*"


def folder(name, spec="*.*"):
    """The path of `spec` in the root's folder `name`, as an application hands fs_input one."""
    return f"A:\\{name}\\{spec}"


# ...and MORE DISKS, each the first with ONE folder more at its root's end: nothing of the first moves, so no machine
# over the first changes when a directory shape is added here (the first has seven clusters left, which bounds each).
# A path into one of these folders is staged over that folder's disk (`disk_of`).
#   DOTTED   a FOLDER WITH AN EXTENSION — the one name whose row the selector must unformat to walk into it;
#   ATTRS    folders and files with ANOTHER ATTRIBUTE BIT: a read-only folder ($11), an archived one ($30) and a
#            plain one among a plain file, a read-only and an archived one — fs_active's folder test is of the
#            SUBDIR bit alone ($fe7874 btst #4);
#   EIGHT3   a hundred names of eight characters and three, in order: the longest names a directory holds, each
#            copied and compared whole — fs_active's dearest read (shuffled, a hundred of them are past one row's
#            budget);
#   THIRTY4  its first thirty-four: the most such names fs_newdir reads, sorts and lists inside one row's budget.
DOTTED = (("SUB", "DIR", SUBDIR_ATTR), ("FILE", "TXT"))
READ_ONLY_ATTR, ARCHIVE_ATTR = fs.GEMDOS_ATTR_READ_ONLY, fs.GEMDOS_ATTR_ARCHIVE
ATTRS = (("PLAIN", "TXT"), ("LOCKED", "", SUBDIR_ATTR | READ_ONLY_ATTR), ("ARCHIVED", "", SUBDIR_ATTR | ARCHIVE_ATTR),
         ("ROFILE", "TXT", READ_ONLY_ATTR), ("ARFILE", "TXT", ARCHIVE_ATTR), ("NORMAL", "", SUBDIR_ATTR))
EIGHT3 = tuple((f"LONGN{index:03d}", "DAT") for index in range(100))
MORE_FOLDERS = {"DOTTED": DOTTED, "ATTRS": ATTRS, "EIGHT3": EIGHT3, "THIRTY4": EIGHT3[:34]}


@functools.cache
def _disk_with(more):
    """The first disk and MORE_FOLDERS' folder `more`."""
    return _disk({**FOLDERS, more: MORE_FOLDERS[more]})


def _first_folder(path):
    """The first name of `path` past its drive: the folder of the root it goes through first (in the root: its spec)."""
    return path.rpartition(":")[2].lstrip("\\").partition("\\")[0]


def disk_of(path):
    """The disk `path` is staged over: the first, or the one that holds the folder it names."""
    first = _first_folder(path)
    return _disk_with(first) if first in MORE_FOLDERS else DISK


# The root as the selector lists it: the base disk's folder and three files (its deleted entry and its volume label
# are no match), then the folders above.
ROOT = (("SUBDIR", "", SUBDIR_ATTR), ("SHORT", "TXT"), ("SPAN", "DAT"), ("EMPTY", "BIN"),
        *((folder, "", SUBDIR_ATTR) for folder in FOLDERS))


def directory(path):
    """The entries of the directory `path` names on its disk (its spec apart): the root's, or a folder's."""
    named = path.rsplit("\\", 1)[0].partition(":")[2].strip("\\")
    return ROOT if not named else () if named == EMPTY_FOLDER else {**FOLDERS, **MORE_FOLDERS}[named]


def listed_name(row):
    """An entry as fs_active keeps it: its kind byte, then NAME.EXT."""
    name, extension = row[:2]
    kind = FOLDER if _attribute(row) & SUBDIR_ATTR else FILE
    return kind + (f"{name}.{extension}" if extension else name).encode()


def disk_machine(disk, pokes=None):
    """The staged drive A: holding `disk`, its root the current directory (`aes_shell.disk_machine`'s, this disk in
    it)."""
    return fs.machine(io.engine(merge_pokes(disk, fs.dmd_pointer_poke(io.DRIVE),
                                            fs.current_directory_poke(io.DRIVE, sh.CURRENT_NODE, fs.ROOT_DND_AT), pokes)))


# ---- the ROM's own fs_input, stopped where a case begins ---------------------------------------------------------------
# A routine's first instruction past its `link a6,#n`: where its frame is read off A6.
LINK_BYTES = 4
FRAME_ARGUMENTS = 8                     # 8(a6): past the saved A6 and the return address
# The budget such a run DECLARES (`aes_event.stopped_at`: past DERIVATION_INSNS' margin, so its own — held to the
# derivations' margin by name), from the deepest MEASURED: the 101-name folder's to its first fs_newdir's return, the
# cursor shown (`test_aes_fslib.py` re-measures it, and holds the declaration to it both ways).
PREFIX_MEASURED_INSNS = 570_391
PREFIX_BUDGET = 3_000_000

Entered = namedtuple("Entered", "machine final registers insns")


def fs_input_machine(path, selection="", shown=False, running=None):
    """What an application's fsel_input(path, selection, &button) starts from: PD0 running as the scheduler makes it —
    the cursor hidden by the application, or `shown` — over the staged disk (the one `path` is on, `disk_of`), the two
    strings and the button word in this module's band. `running`: another ROM-made machine whose running process
    makes the call (pokes: one only a run through the dispatcher makes — the screen's lock another process's)."""
    if running is None:
        running = aes_event.shown_machine() if shown else aes_event.machine()
    staged = disk_machine(disk_of(path), merge_pokes(aes.leaf_machine(), running, STALE_ANSWERS, STALE_SLOTS,
                                                     sh.text(PATH_AT, path, PATH_BYTES),
                                                     sh.text(FILE_AT, selection, FILE_BYTES)))
    # `savptr` LAST: the scheduler's run restored the snapshot's own, and the BIOS traps under GEMDOS must save their
    # registers in the band no differential compares (`gemdos.machine`).
    return merge_pokes(staged, aes_event.savptr_in_the_band())


@functools.cache
def stopped(stop, path, selection="", shown=False):
    """The ROM's own fs_input(`path`, `selection`, &button) run until it first reaches `stop`: the machine it leaves —
    what it WROTE laid over the one it started from, its own stack out — with the run's final RAM (`ram_in`: every
    prefix is kept for its process's life) and registers. A derivation, kept by content — the budget it is held to
    (PREFIX_BUDGET, as it stands when asked) among its inputs."""
    return _stopped(stop, path, selection, shown, PREFIX_BUDGET)


@derived.kept
def _stopped(stop, path, selection, shown, budget):
    start = fs_input_machine(path, selection, shown)
    frame = aes_event.frame_of(("l", PATH_AT), ("l", FILE_AT), ("l", BUTTON_AT))
    final, writes, registers = aes_event.stopped_at(make_image(merge_pokes(start, {abi.FIRST_ARG: frame})),
                                                    addrs.AES_ROM_FS_INPUT, stop, budget)
    return Entered(merge_pokes(start, case.written_by(writes)), ram_in(final), registers, registers["ninsns"])


def entered(name, path, selection="", shown=False):
    """...until it first ENTERS the routine `addrs.<name>` (past its `link`): `(machine, frame)` — `frame(offset)` the
    longword and `frame.word(offset)` the word at that offset of the routine's own frame, as its caller pushed it."""
    run = stopped(getattr(addrs, name) + LINK_BYTES, path, selection, shown)
    return run.machine, Frame(run.final, run.registers["a6"] + FRAME_ARGUMENTS)


class Frame:
    """A routine's arguments, read off its `link`ed frame in the ROM's run."""

    def __init__(self, memory, at):
        self.memory, self.at = memory, at

    def __call__(self, offset):
        return case.long_in(self.memory, self.at + offset)

    def word(self, offset):
        return aes.signed(case.word_in(self.memory, self.at + offset))


# WHERE EACH ARGUMENT IS in a routine's frame as its caller pushed it (`Frame`'s offsets, `fslib.h`'s signatures):
# longwords for fs_back(path, end) — and fs_pspec, the same —, fs_active(path, spec, &count) and fs_newdir(title, path,
# spec, tree, &count), whose count's pointer aims into fs_input's own frame and is replaced by COUNT_AT (the module's
# docstring); fs_format(tree, top, count) a longword and two words; fs_sel(row, state) two words.
BACK_PATH, BACK_END = 0, LONG_BYTES
ACTIVE_PATH, ACTIVE_SPEC = 0, LONG_BYTES
NEWDIR_TITLE, NEWDIR_PATH, NEWDIR_SPEC, NEWDIR_TREE = (argument * LONG_BYTES for argument in range(4))
FORMAT_TREE, FORMAT_TOP, FORMAT_COUNT = 0, LONG_BYTES, LONG_BYTES + WORD_BYTES
SEL_ROW, SEL_STATE = 0, WORD_BYTES


def active_arguments(frame, count_at=None):
    """fs_active's arguments as fs_input hands them (`frame`: `entered(ACTIVE, ...)`'s), the count at COUNT_AT."""
    return frame(ACTIVE_PATH), frame(ACTIVE_SPEC), COUNT_AT if count_at is None else count_at


def newdir_arguments(frame):
    """fs_newdir's (`frame`: `entered(NEWDIR, ...)`'s), the count at COUNT_AT."""
    return frame(NEWDIR_TITLE), frame(NEWDIR_PATH), frame(NEWDIR_SPEC), frame(NEWDIR_TREE), COUNT_AT


# fs_input's frame, where its first fs_newdir returned ($fe7fd6): the count it handed fs_newdir by address — -6(a6)
# ($fe7fc2 subq.l #6,(sp)), `fslib.h`'s FS_INPUT_COUNT from where its layout of that frame starts, -38(a6).
INPUT_FRAME_FROM_A6 = -38               # ($fe7e12 addi.l #-38: the frame's lowest word handed on by address)
COUNT_FROM_A6 = INPUT_FRAME_FROM_A6 + FS["FS_INPUT_COUNT"]
Listed = namedtuple("Listed", "machine count final insns")


def listed(path, selection="", shown=False):
    """...until its first fs_newdir has returned: the directory read, sorted, its first rows in the list, the selector
    drawn — and how many names it kept. What fs_format, fs_sel and fs_nscroll run over."""
    run = stopped(addrs.AES_FS_INPUT_NEWDIR_RETURN, path, selection, shown)
    count = aes.signed(case.word_in(run.final, run.registers["a6"] + COUNT_FROM_A6))
    return Listed(run.machine, count, run.final, run.insns)


# ---- the doors, and the runs ----------------------------------------------------------------------------------------------
def _cconout(buf, arguments, _argument_bytes):
    return console.CCONOUT.core(buf, case.word_in(buf, arguments))


HANDLERS = {
    **sh.HANDLERS,
    gemdos.rom_handler(addrs.GEMDOS_FSNEXT_FN): fs.leaf_handler(fs.FSNEXT),
    gemdos.rom_handler(addrs.GEMDOS_CCONOUT_FN): _cconout,
}


def drawing_hooks():
    """The two doors a draw goes out by: the VDI, and just_draw handed to ob_draw's walk."""
    return gsx.vdi_hook, aes.alcyon_object_hook(aes.walkers(od.JUST_DRAW))


def drawing_doors():
    """...as ONE `aes.run_function` hook: a routine that draws and makes no `trap #1` (fs_sel, fs_nscroll)."""
    return aes.doors(*drawing_hooks())


def doors():
    """Every door a selector routine's C goes out by, as one hook: the staged disk and GEMDOS's handlers (`aes_shell`'s,
    with Fsnext and Cconout), and the drawing doors."""
    return aes.doors(sh.staged_disk, functools.partial(gemdos.bound_handlers, HANDLERS), *drawing_hooks())


# The longest run of a case, MEASURED: fs_newdir over the 101-name folder, the cursor shown (the read, the sort of a
# hundred names, four draws) — past the oracle's default 200,000 (`test_aes_fslib.py` re-measures it).
RUN_MEASURED_INSNS = 404_624
# ...and the cap every such run is under: the BATTERY's, declared from that measure on the one mechanism
# (`aes_event.battery_cap`: needed, the derivations' margin under it, no more than their stale bound over it) — each
# run then held to its margin by name, at the one door (`aes_event.capped_run`).
RUN_CAP = aes_event.battery_cap(3_000_000, deepest=RUN_MEASURED_INSNS)


def run(name, arguments, machine, pokes=None, *, cap=None, **kwargs):
    """`addrs.<name>` over `machine` (a ROM run's, above) and `pokes`, against its core — REAL GEMDOS and the VDI on
    both shores, the GEMDOS door's windows and the mask word dropped where the ROM's run stores them, unpoisoned;
    under the battery's declared cap (RUN_CAP) — or the case's own `cap`, held as any case's is (`aes_event.capped_run`)."""
    staged = merge_pokes(machine, STALE_ANSWERS, STALE_SLOTS, pokes)
    return aes_event.capped_run(name, RUN_CAP if cap is None else cap, kwargs, lambda **limits: aes.run_function(
        name, arguments, staged, hook=doors(), dropped_windows=sh.REAL_WINDOWS, poison=False, result=sh.Result, **limits))


# ---- what a run left: the names, the index, the list ---------------------------------------------------------------------
def kept_names(image, count):
    """The names fs_active left, in the index's order: each from the names block at its offset."""
    names, index = case.long_in(image, FS["AES_AD_FSNAMES"]), case.long_in(image, FS["AES_AD_FSINDEX"])
    found = []
    for entry in range(count):
        found.append(aes_strings.string_in(image, names + case.long_in(image, index + entry * FS["FS_INDEX_ENTRY_BYTES"])))
    return found


def sorted_names(rows):
    """What fs_active keeps of `rows` under "*.*" and in what order: the first NAMES_KEPT of them, in the directory's
    order — then sorted bytewise, kind first (a folder's 7 before a file's space)."""
    return sorted([listed_name(row) for row in rows][:NAMES_KEPT])


def row_texts(image, tree=SELECTOR):
    """The list's nine rows' texts, as the tree's TEDINFOs hold them."""
    return [aes_strings.string_in(image, case.long_in(image, od.object_long(tree, FIRST_NAME + row, "SPEC", image) + aes.TE_PTEXT))
            for row in range(ROWS)]


# ---- GEMDOS REPLAYED: what Tier 3 prices -------------------------------------------------------------------------------
# Real GEMDOS cannot be priced (`aes_shell`: the trap entry's register save differs between the shores by nature, and a
# Tier 3 companion compares everything). So a priced row's `trap #1` vector names a 68000 HANDLER staged here that
# REPLAYS the ROM's own GEMDOS: it RECORDS each call — its function word and its frame — in a ledger, keeps the DTA
# Fsetdta names, and answers the next entry of a SCRIPT: the longword D0, and for Fsfirst and Fsnext the 44 bytes the
# DTA is left holding. The script is DERIVED, never typed (`replay_script`): the ROM's GEMDOS itself, called by a real
# `trap #1` function by function over the same machine and disk, each call's D0 and DTA kept. The host twin is the same
# effect over the candidate's image.
#
# NOT `aes_shell`'s scripted trap, which this cannot extend: that one's script is answers alone (a search there leaves
# the DTA as staged), its frames are at least a word, and adding a function to it would move every row it prices. So
# the 68000 handler is this module's own — and the two TABLES it walks, the ledger and the script, are `aes_shell.Table`s
# as that one's are: staged, bounded, recorded, stepped and read back by the one spelling.
REPLAY_OFFSET = 0x2000                  # between test/aes_strings.py's band and the menu layer's: the handler and its ledger
REPLAY_BYTES = 0x500
REPLAY_AT = aes.SPAN.claim(aes.WINDOW_AT + REPLAY_OFFSET, REPLAY_BYTES,
                           "test/aes_fslib.py: GEMDOS replayed — the handler and its ledger")
SCRIPT_OFFSET = 0x4000                  # the window's last 8 KB, added for it: the script
SCRIPT_BYTES = 0x1900
SCRIPT_BAND_AT = aes.SPAN.claim(aes.WINDOW_AT + SCRIPT_OFFSET, SCRIPT_BYTES,
                                "test/aes_fslib.py: GEMDOS replayed — the script")
DTA_BYTES = 44                          # what a search fills: its 21 reserved bytes, the attribute, time, date, length, name
HANDLER_BYTES = 0xA0
# A whole session of fs_input over a hundred names is 111 calls — three Mallocs, Fsetdta, 103 searches, the bell, three
# Mfrees — and the rest is room for what a user does in it short of a second read of such a directory.
REPLAY_CALLS = 128
RECORDED_ARGUMENT_BYTES = 6             # Fsfirst's frame, the widest here: its path and its attribute word
LEDGER_ENTRY_BYTES = WORD_BYTES + RECORDED_ARGUMENT_BYTES
SCRIPT_ENTRY_BYTES = LONG_BYTES + DTA_BYTES
HANDLER_AT = REPLAY_AT
DTA_CELL_AT = HANDLER_AT + HANDLER_BYTES            # the DTA the last Fsetdta named
LEDGER_AT = DTA_CELL_AT + LONG_BYTES                # the ledger's pointer, then its entries
LEDGER_ENTRIES_AT = LEDGER_AT + LONG_BYTES
assert LEDGER_ENTRIES_AT + REPLAY_CALLS * LEDGER_ENTRY_BYTES <= REPLAY_AT + REPLAY_BYTES
SCRIPT_AT = SCRIPT_BAND_AT                          # the script's pointer, then its entries
SCRIPT_ENTRIES_AT = SCRIPT_AT + LONG_BYTES
assert SCRIPT_ENTRIES_AT + REPLAY_CALLS * SCRIPT_ENTRY_BYTES <= SCRIPT_BAND_AT + SCRIPT_BYTES
LEDGER = sh.Table(LEDGER_AT, REPLAY_CALLS, LEDGER_ENTRY_BYTES, "replay's ledger")
SCRIPT = sh.Table(SCRIPT_AT, REPLAY_CALLS, SCRIPT_ENTRY_BYTES, "replay's script")
assert (LEDGER.first, SCRIPT.first) == (LEDGER_ENTRIES_AT, SCRIPT_ENTRIES_AT)
FSETDTA, FSFIRST, FSNEXT, CCONOUT_FN = (addrs.GEMDOS_FSETDTA_FN, addrs.GEMDOS_FSFIRST_FN, addrs.GEMDOS_FSNEXT_FN,
                                        addrs.GEMDOS_CCONOUT_FN)
SEARCHES = (FSFIRST, FSNEXT)
# How many bytes of a call's frame are its own, by function: the rest of an entry is zeros (above a shorter frame lies
# its caller's stack, which no C build reproduces).
ARGUMENT_BYTES = {FSNEXT: 0, CCONOUT_FN: WORD_BYTES, FSETDTA: LONG_BYTES, FSFIRST: LONG_BYTES + WORD_BYTES}
# ...and for a whole SESSION of fs_input, which Mallocs its three blocks before any search and frees them after: the
# same handler with the two more functions told apart (`replay_handler(SESSION_ARGUMENT_BYTES)`). A handler of its own
# rather than those two added to the one above: the rows that one prices would each move by the two compares.
MALLOC, MFREE = addrs.GEMDOS_MALLOC_FN, addrs.GEMDOS_MFREE_FN
SESSION_ARGUMENT_BYTES = {**ARGUMENT_BYTES, MALLOC: LONG_BYTES, MFREE: LONG_BYTES}
DBF_BACK_TO_THE_MOVE = -4               # `dbf d1` to the `move.b` above it


def _long(value):
    return struct.pack(">I", value)


# Where the handler finds the call it serves, past the A0 it pushed: the function word, then the call's own frame.
FUNCTION_IN_FRAME = vdi_helpers.FRAME_WORDS_AT
ARGUMENTS_IN_FRAME = FUNCTION_IN_FRAME + WORD_BYTES


def _is_function(function):
    """`cmpi.w #function,<the call's function word>`."""
    return vdi.pack_words(op.CMPI_W_STACK, function, FUNCTION_IN_FRAME)


def _recording(argument_bytes):
    """The handler's first half: the function word into the ledger, then its frame a word at a time — each function
    whose frame ends sooner branching out to the zeros that pad it; the ledger's pointer stored back."""
    pieces = [vdi_helpers.PUSH_A0 + vdi_helpers.MOVEA_L_ABSOLUTE_A0 + _long(LEDGER_AT),
              vdi.pack_words(op.MOVE_W_STACK_TO_A0_POSTINC, FUNCTION_IN_FRAME)]
    for recorded in range(0, RECORDED_ARGUMENT_BYTES, WORD_BYTES):
        for function in (function for function, size in argument_bytes.items() if size == recorded):
            pieces += [_is_function(function), (op.BEQ_S, f"pad {recorded}")]
        pieces.append(vdi.pack_words(op.MOVE_W_STACK_TO_A0_POSTINC, ARGUMENTS_IN_FRAME + recorded))
    pieces.append((op.BRA_S, "recorded"))
    for recorded in range(0, RECORDED_ARGUMENT_BYTES, WORD_BYTES):       # each falls through into the shorter pads
        pieces += [("label", f"pad {recorded}"), vdi.pack_words(op.CLR_W_A0_POSTINC)]
    return pieces + [("label", "recorded"), vdi_helpers.STORE_A0_ABSOLUTE + _long(LEDGER_AT)]


def _answering():
    """...and its second: Fsetdta's longword kept; D0 the script's next longword; for a search, the entry's 44 bytes
    copied to the DTA — for any other call stepped over; the script's pointer stored back; `rte`."""
    fill_the_dta = (vdi.pack_words(op.PUSH_A1, op.PUSH_D1, op.MOVEA_L_ABSOLUTE_A1) + _long(DTA_CELL_AT)
                    + vdi.pack_words(op.MOVEQ_D1 | (DTA_BYTES - 1), op.MOVE_B_A0_TO_A1, op.DBF_D1,
                                     DBF_BACK_TO_THE_MOVE & 0xFFFF, op.POP_D1, op.POP_A1))
    return [_is_function(FSETDTA), (op.BNE_S, "answer"),
            vdi.pack_words(op.MOVE_L_STACK_TO_ABSOLUTE, ARGUMENTS_IN_FRAME) + _long(DTA_CELL_AT),
            ("label", "answer"),
            vdi_helpers.MOVEA_L_ABSOLUTE_A0 + _long(SCRIPT_AT) + vdi.pack_words(op.MOVE_L_A0_POSTINC_D0),
            _is_function(FSFIRST), (op.BEQ_S, "fill"), _is_function(FSNEXT), (op.BEQ_S, "fill"),
            vdi.pack_words(op.LEA_D16_A0_A0, DTA_BYTES), (op.BRA_S, "answered"),
            ("label", "fill"), fill_the_dta,
            ("label", "answered"), vdi_helpers.STORE_A0_ABSOLUTE + _long(SCRIPT_AT) + vdi_helpers.POP_A0 + op.RTE]


def replay_handler(argument_bytes=None):
    """The handler: each call recorded in the ledger (`_recording`), then answered from the script (`_answering`).
    Every register but D0 as found. `argument_bytes`: the functions it tells apart, each with its frame's bytes
    (ARGUMENT_BYTES by default; a session's, SESSION_ARGUMENT_BYTES)."""
    return sh.laid_out(_recording(ARGUMENT_BYTES if argument_bytes is None else argument_bytes) + _answering())


assert len(replay_handler()) <= len(replay_handler(SESSION_ARGUMENT_BYTES)) <= HANDLER_BYTES
NO_DTA = bytes([vdi.FILL]) * DTA_BYTES           # the 44 bytes of an entry no search reads
Call = namedtuple("Call", "function frame")


def replay_pokes(script, dta=None, argument_bytes=None):
    """The trap vector at the handler, an empty ledger (its entries FILLed), the DTA Fsetdta has named so far (`dta`;
    none yet: STALE) and the script — `(D0, the 44 bytes a search leaves in the DTA)` per call. `argument_bytes`:
    the handler's functions (`replay_handler`)."""
    assert len(script) <= REPLAY_CALLS, f"{len(script)} calls: more than the replay's band holds"
    entries = b"".join(_long(answer & 0xFFFF_FFFF) + filled for answer, filled in script)
    return {addrs.VECTOR_TRAP_GEMDOS: _long(HANDLER_AT), HANDLER_AT: replay_handler(argument_bytes),
            DTA_CELL_AT: _long(vdi.STALE_LONG if dta is None else dta), **LEDGER.staged(), **SCRIPT.staged(entries)}


def _replayed(function):
    """The handler's HOST TWIN for `function`: the same ledger entry, DTA cell, answer and DTA bytes — both tables'
    pointers bounded before anything is stored (`aes_shell.Table`)."""
    def handler(buf, arguments, _argument_bytes):
        entry, script = LEDGER.next(buf), SCRIPT.next(buf)
        frame = LEDGER.record(buf, entry, function, arguments, SESSION_ARGUMENT_BYTES[function])
        if function == FSETDTA:
            isr.poke(buf, DTA_CELL_AT, frame[:LONG_BYTES])
        if function in SEARCHES:
            isr.poke(buf, case.long_in(buf, DTA_CELL_AT) & OS_BUS_ADDR_MASK,
                     ctypes.string_at(ctypes.addressof(buf.contents) + script + LONG_BYTES, DTA_BYTES))
        SCRIPT.step(buf, script)
        return case.long_in(buf, script)
    return handler


REPLAY_HANDLERS = {gemdos.rom_handler(function): _replayed(function) for function in SESSION_ARGUMENT_BYTES}


def replay_doors():
    """`doors()` with GEMDOS replayed: the twin bound for the six functions the selector calls (REPLAY_HANDLERS: the
    two searches, Fsetdta, the bell's Cconout, Malloc and Mfree), no disk."""
    return aes.doors(functools.partial(gemdos.bound_handlers, REPLAY_HANDLERS), *drawing_hooks())


def replay_calls(image):
    """The ledger in `image` as `[Call(function, frame bytes), ...]`, in the order the calls were made."""
    return [Call(function, frame) for function, frame in LEDGER.recorded(image)]


def call(function, *fields):
    """A ledger entry for fields given as ('w', value) / ('l', value), zero-padded as the handler pads it."""
    return Call(function, LEDGER.frame(*fields))


# ---- the script, DERIVED: the ROM's own GEMDOS, one real `trap #1` at a time ------------------------------------------------
def _trapped(memory, function, words):
    """The ROM's GEMDOS `function` called by a real `trap #1` with the argument `words`, over `memory`: `(D0, the
    memory after, what the call wrote)`. `memory` is the CALLER's OWN buffer — a fresh image, or the memory the call
    before left — and the trap's caller is staged in it IN PLACE: a copy first was sixteen megabytes more per call."""
    caller = gemdos.trap_caller(function, words)
    image = memory if isinstance(memory, bytearray) else bytearray(memory)
    image[trap.TRAP_CALLER_AT:trap.TRAP_CALLER_AT + len(caller)] = caller
    final, writes, registers = emu.run(image, trap.TRAP_CALLER_AT)
    return registers["d0"], final, writes


def gemdos_call(memory, function, *words):
    """...over `memory` (a machine's image, or the memory the call before it left): `(D0, the memory after)`."""
    answer, final, _writes = _trapped(memory, function, words)
    return answer, final


def found(answer):
    """dos_sfirst's and dos_snext's own test: the answer's WORD is 0."""
    return not answer & 0xFFFF


@functools.cache
@derived.kept
def whole_search(path, shown=False):
    """Every GEMDOS answer a search of the directory fs_input's first fs_active reads over `path` can get: Fsetdta's,
    then Fsfirst's and each Fsnext's to the one that finds no more — `(D0, the DTA after)` each, every call over
    the memory the one before it left."""
    machine, frame = entered(ACTIVE, path, shown=shown)
    memory = make_image(machine)
    dta = case.long_in(memory, FS["AES_AD_FSDTA"])
    answer, memory = gemdos_call(memory, FSETDTA, *gemdos.long_words(dta))
    script = [(answer, NO_DTA)]
    answer, memory = gemdos_call(memory, FSFIRST, *gemdos.long_words(frame(ACTIVE_PATH)), FS["FS_SEARCH_ATTRIBUTES"])
    script.append((answer, bytes(memory[dta:dta + DTA_BYTES])))
    while found(answer):
        answer, memory = gemdos_call(memory, FSNEXT)
        script.append((answer, bytes(memory[dta:dta + DTA_BYTES])))
    return tuple(script)


@functools.cache
@derived.kept
def bell_answer(path, shown=False):
    """...and what the ROM's Cconout of BEL answers over the same machine."""
    machine, _frame = entered(ACTIVE, path, shown=shown)
    return gemdos_call(make_image(machine), CCONOUT_FN, addrs.CON_BEL)[0]


@functools.cache
@derived.kept
def replay_script(path, shown=False):
    """The calls fs_active MAKES of that search, as the ROM's own run of it over the whole search makes them (its
    ledger): the search's answers up to the last it asks for, and the bell's where it rings."""
    machine, frame = entered(ACTIVE, path, shown=shown)
    whole = whole_search(path, shown)
    staged = merge_pokes(machine, STALE_ANSWERS, replay_pokes(whole))
    final, _writes, ran = emu.run(make_image(aes.staged(ACTIVE, active_arguments(frame), staged)),
                                  getattr(addrs, ACTIVE), max_insns=RUN_CAP.insns)
    aes_event.vet_the_cap(getattr(addrs, ACTIVE), ran["ninsns"], RUN_CAP)
    made = replay_calls(final)
    script = list(whole[:len(made)])
    if made[-1].function == CCONOUT_FN:
        script = script[:len(made) - 1] + [(bell_answer(path, shown), NO_DTA)]
    assert len(script) == len(made), f"fs_active made {len(made)} calls and the search answers {len(whole)}"
    return tuple(script)


def replayed(name, path, shown=False):
    """`entered(name, path)` — fs_active or fs_newdir — with GEMDOS replayed: `(machine, frame)`."""
    machine, frame = entered(name, path, shown=shown)
    return merge_pokes(machine, replay_pokes(replay_script(path, shown))), frame


def run_replayed(name, arguments, machine, pokes=None, *, cap=None, door=None, **kwargs):
    """`run` over a replayed machine: the same routine and machine, the script in GEMDOS's place — the run Tier 3
    prices, with nothing dropped but the mask word. `door`: the C's doors where a case wraps the replay's own
    (`replay_doors()`)."""
    staged = merge_pokes(machine, STALE_ANSWERS, STALE_SLOTS, pokes)
    return aes_event.capped_run(name, RUN_CAP if cap is None else cap, kwargs, lambda **limits: aes.run_function(
        name, arguments, staged, hook=door or replay_doors(), poison=False, **limits))


def register(label, name, arguments, machine, pokes=None, *, door=None, through_line_f=False):
    """One `VERIFIED_CASES` row over a selector machine (`aes.register`) — its answer words and the C's frames stale
    as `fs_input_machine` staged them — its companion's C going out by `door` (`drawing_doors()`, or `replay_doors()`
    for a routine that traps: its machine a replayed one)."""
    aes.register(label, name, arguments, merge_pokes(machine, pokes) if pokes else machine, hook=door,
                 through_line_f=through_line_f)


# ---- fs_input ITSELF: whole sessions -----------------------------------------------------------------------------------
# fs_input waits (fm_do's ev_multi, gr_slidebox's), so a case of it is a SESSION: the routine over `fs_input_machine`,
# taken through interrupts the ROM's own ISRs deliver at its waits (`aes_event.interrupted`) — the C in a child, held
# to the ROM byte for byte, then through the bench's second differential. Both need GEMDOS on the C's side where no
# staged disk can follow (a child binds no pass; the bench's trap entry saves registers that differ by nature,
# `aes_shell`): so a session runs over GEMDOS REPLAYED, the whole of it — its three Mallocs, every search of every
# directory it reads, the bell, its three Mfrees. The script is DERIVED from the session itself over REAL GEMDOS
# (`session_script`): the ROM's fs_input run over the staged disk through the same interrupts, WATCHED at GEMDOS's own
# trap handler (`GemdosCalls`), and at each call it makes the ROM's GEMDOS called by a real `trap #1` over the memory
# as it stands there (`gemdos_call`) — its D0 and, for a search, the DTA it leaves. `test_aes_fs_input.py` holds the
# replayed run to the real disk's: the same answers, strings and screen.
ARGUMENTS = (PATH_AT, FILE_AT, BUTTON_AT)
GEMDOS_TRAP = aes_event.GEMDOS_TRAP
EXCEPTION_FRAME_BYTES = aes_event.EXCEPTION_FRAME_PC + LONG_BYTES   # the status register's word and the return PC
# A session's DECLARED budgets (`aes_event`'s `budget=`: held to 5 N <= B <= 10 N over a run of N instructions): four
# classes that between them admit every session from 300,000 to 1,800,000 instructions — the middle one for a session
# whose two runs (over the staged disk, which spends more inside GEMDOS, and over the replay) straddle 600,000.
SESSION_INSNS = 3_000_000
MIDDLE_SESSION_INSNS = 4_500_000
LONG_SESSION_INSNS = 6_000_000
LONGER_SESSION_INSNS = 9_000_000


class GemdosCalls(aes_event.DoorStops):
    """A watch over the ROM's fs_input (`aes_event.run_watched`) that also stops at GEMDOS's trap handler — outside
    any door call, as a marked trap is (`aes_event.Timeline`) — and keeps each call there: `made`, a list of
    `(function, frame bytes, the RAM at the call)` (`ram_in`: what the re-enactment of the call and every reader of it
    needs, a megabyte where the whole image is sixteen). With `loop_at`, a PC of fs_input's own loop, it stops there
    too and keeps what the run has spent and its RAM at each arrival (`passes`), ENDING the run at the arrival of
    ordinal `last_pass` (as a call that blocks ends one, `aes_event.Blocked`): for a run that never returns.

    BLIND FROM `loop_at` TO THE NEXT PASS'S HEAD: a stop is taken before its instruction, so past an arrival at
    `loop_at` the watch arms the pass's head (AES_FS_INPUT_PASS) ALONE until the run reaches it — no door entry, no
    GEMDOS call, no dispatcher. A run that makes a door call in that stretch (a pass that drags the elevator:
    gr_slidebox's waits lie there) is delivered nothing at it and never seen to block: it runs on to its budget, and
    `looping` names this stretch in that refusal. Neither use today makes one (fm_do is at the pass's head, the
    directory's read before `loop_at`)."""

    def __init__(self, delivered, argument_bytes, loop_at=None, last_pass=0):
        super().__init__(aes_event.ENTRIES, aes_event.ROM_RETURNS, blocks=True, delivered=delivered)
        self.marked_with(aes_event.Timeline((GEMDOS_TRAP,)))
        self._argument_bytes, self.made = argument_bytes, []
        self._loop_at, self._last_pass, self.passes = loop_at, last_pass, []
        if loop_at is not None:
            self.first |= {loop_at}

    def stopped(self, pc, sp, memory):
        if pc == addrs.AES_FS_INPUT_PASS and self._loop_at is not None:
            return self.first           # the next pass begun: `loop_at` watched again
        if pc == self._loop_at and self.between_calls:
            self.passes.append((aes_event.run_cost()["insns"], ram_in(memory)))
            if len(self.passes) > self._last_pass:
                raise aes_event.Blocked(f"the run was ended at its arrival {self._last_pass} at {pc:#x}")
            # A stop is taken BEFORE its instruction: watched again at once, the run would stop here without moving.
            return frozenset({addrs.AES_FS_INPUT_PASS})
        if pc == GEMDOS_TRAP:
            function = case.word_in(memory, sp + EXCEPTION_FRAME_BYTES)
            assert function in self._argument_bytes, f"fs_input called GEMDOS function {function:#x}: none the replay serves"
            frame_at = sp + EXCEPTION_FRAME_BYTES + WORD_BYTES
            self.made.append((function, bytes(memory[frame_at:frame_at + self._argument_bytes[function]]), ram_in(memory)))
        return super().stopped(pc, sp, memory)


# WHAT IS KEPT OF A RUN'S MEMORY is its RAM: above it the address space is the ROM and the hardware's page, which no
# run of the selector changes — held by name wherever a memory is kept (`ram_in`), so that the whole image can be put
# back (`whole_image`) for the one consumer that runs over it. Kept whole, a session over a hundred names held 111
# images of sixteen megabytes at once (measured: 2.1-2.35 GB peak in every process that imports the registry).
RAM_BYTES = addrs.ST_RAM_BYTES
_ABOVE_RAM = bytes(BASE_IMAGE[RAM_BYTES:])
_ABOVE_RAM_BYTES = len(_ABOVE_RAM)
_memcmp = ctypes.CDLL(None).memcmp
_memcmp.argtypes, _memcmp.restype = (ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t), ctypes.c_int


def _above_ram_is_the_snapshot_s(memory):
    """Is `memory` (the whole image) the snapshot's above its RAM? Compared IN PLACE where the memory is a run's own
    buffer: a copy of fifteen megabytes per kept memory was most of what keeping one cost, and two memoryviews
    compare an element at a time (measured: 3.9 CPU-s more over the 273 GEMDOS calls of the four priced sessions)."""
    if not isinstance(memory, bytearray):
        return memoryview(memory)[RAM_BYTES:].tobytes() == _ABOVE_RAM
    above = (ctypes.c_char * _ABOVE_RAM_BYTES).from_buffer(memory, RAM_BYTES)
    return _memcmp(ctypes.addressof(above), _ABOVE_RAM, _ABOVE_RAM_BYTES) == 0


def ram_in(memory):
    """The RAM of a run's `memory` (the whole image), as bytes — refused where the memory is not the whole image, or
    the run changed a byte above its RAM."""
    assert len(memory) == len(BASE_IMAGE), (
        f"a memory of {len(memory)} bytes is not the whole image ({len(BASE_IMAGE)}): what lies above its RAM is not known")
    assert _above_ram_is_the_snapshot_s(memory), "the run changed memory above the machine's RAM: keep it whole"
    return memoryview(memory)[:RAM_BYTES].tobytes()


def whole_image(ram):
    """...and the whole image again: `ram` under the snapshot's own ROM and hardware page."""
    image = bytearray(BASE_IMAGE)
    image[:RAM_BYTES] = ram
    return image


Script = namedtuple("Script", "answers functions memory frames")


def _frame_words(frame):
    return struct.unpack(f">{len(frame) // WORD_BYTES}H", frame)


def answers_of(made):
    """The replay's script for the GEMDOS calls `made` (`GemdosCalls.made`): each answered by the ROM's own GEMDOS,
    called by a real `trap #1` over the memory as it stood at the call — its D0 and, for a search, the DTA it leaves."""
    script = []
    for function, frame, at_the_call in made:
        answer, after = gemdos_call(whole_image(at_the_call), function, *_frame_words(frame))
        dta = case.long_in(at_the_call, FS["AES_AD_FSDTA"]) & OS_BUS_ADDR_MASK
        script.append((answer, bytes(after[dta:dta + DTA_BYTES]) if function in SEARCHES else NO_DTA))
    return tuple(script)


def _watched(watch, machine, budget, arguments=ARGUMENTS):
    """The ROM's own fs_input over `machine` (the frame `arguments` staged) run under `watch` and `budget`
    (`aes_event.run_watched`): `(did it return — False where the watch ended it —, the memory it left)`."""
    memory = make_image(aes.staged(INPUT, arguments, machine))
    return aes_event.run_watched(memory, addrs.AES_ROM_FS_INPUT, watch, budget=budget) is not None, memory


@derived.kept
def session_script(machine, interrupts, budget, arguments=ARGUMENTS, blocks=False):
    """The GEMDOS calls the ROM's fs_input makes over `machine` (a REAL-disk one, `fs_input_machine`) taken through
    `interrupts`, each answered by the ROM's own GEMDOS over the memory at the call: `Script(answers, functions,
    memory, frames)` — the replay's script (`replay_pokes`), the function each call is, in order, the RAM the
    real-disk run left (`ram_in`), and THE FRAME EACH CALL WAS HANDED (its own bytes: what the answer was given
    TO — a run answered from this script must hand the same, `frames_as_recorded`). `blocks`: the session is one
    that ends WAITING (nothing delivered at its last wait), its memory then the run's as it reached the dispatcher."""
    delivered = aes_event.deliveries(INPUT, arguments, machine, interrupts, budget)
    watch = GemdosCalls(delivered, SESSION_ARGUMENT_BYTES)
    returned, memory = _watched(watch, machine, budget, arguments)
    assert returned != blocks, f"the session {'returned' if returned else 'blocks'}: the premise was the other"
    return Script(answers_of(watch.made), tuple(function for function, _frame, _memory in watch.made), ram_in(memory),
                  tuple(frame for _function, frame, _memory in watch.made))


def frames_as_recorded(script):
    """`script`'s frames as the replay's ledger records a call's (`replay_calls`): zero-padded to an entry's width."""
    return tuple(frame.ljust(RECORDED_ARGUMENT_BYTES, b"\0") for frame in script.frames)


def looping(machine, last_pass, budget=None, delivered=None):
    """The ROM's fs_input over `machine` (a real-disk one) run to its arrival of ordinal `last_pass` at the head of
    the pass that reads no directory (AES_FS_INPUT_NO_READ, where its first pass arrives when the path is the one
    last read) and ended there: `(script, passes)` — the replay's script for the GEMDOS calls it made, and at each
    arrival `(the instructions run so far, the memory)`. `budget`: the run's own, declared where it needs one
    (`aes_event`'s `budget=`: a run ended at a pass is a run that ENDED, held both ways — and refused a declaration
    where the default admits it, as the run to the empty path's second pass is admitted). `delivered`: what is laid
    at its door calls on the way (`aes_event.deliveries`), for a run that waits before it loops."""
    watch = GemdosCalls(delivered or {}, SESSION_ARGUMENT_BYTES, addrs.AES_FS_INPUT_NO_READ, last_pass)
    try:
        returned, _memory = _watched(watch, machine, budget)
    except (RuntimeError, AssertionError) as refused:
        if "budget" not in str(refused):
            raise
        raise AssertionError(
            f"{refused} — BUT this run was ended at no pass after its arrival {len(watch.passes)} at the pass that "
            f"reads nothing, and past such an arrival it is watched at the next pass's head ALONE (`GemdosCalls`): a "
            f"door call it made on the way was delivered nothing and not seen to block. A pass that waits (a drag) "
            f"cannot be looped over, whatever its budget") from None
    assert not returned, "fs_input returned"
    return answers_of(watch.made), watch.passes


def replay_machine(machine, script):
    """`machine` with GEMDOS replayed from `script` (`session_script`): the session's own handler."""
    return merge_pokes(machine, replay_pokes(script, argument_bytes=SESSION_ARGUMENT_BYTES))


# THE REPLAY IN A CHILD (`aes_event.declare_child_doors`): the C's GEMDOS dispatcher calls its handlers through a hook
# no pass opens there, so the twin handlers are bound for the child's one call, any other handler ENDING it by name.
CHILD_GEMDOS_REFUSED = 7                # the child's exit status then: apart from `aes_event`'s CHILD_*_REFUSED
GEMDOS_HANDLER_HOOK = "recreate_call_gemdos_handler"    # the dispatcher's hook, by its name in the candidate
_CHILD_TRAMPOLINES = []


def bind_replay_in_a_child(lib):
    """The replay's host twins (REPLAY_HANDLERS) bound into `lib`, the candidate the child loaded."""
    def dispatch(buf, handler, arguments, argument_bytes):
        try:
            assert handler in REPLAY_HANDLERS, (
                f"the candidate called GEMDOS handler {handler:#x}, which the replay does not serve")
            return REPLAY_HANDLERS[handler](buf, arguments, argument_bytes)
        except Exception as refused:    # a callback cannot raise into C: the child ends here, by name
            print(refused, file=sys.stderr, flush=True)
            os._exit(CHILD_GEMDOS_REFUSED)
    trampoline = gemdos.CALL_HANDLER(dispatch)
    _CHILD_TRAMPOLINES.append(trampoline)
    bind_pointer(GEMDOS_HANDLER_HOOK, trampoline, lib)


aes_event.declare_child_doors(INPUT, "import aes_fslib; aes_fslib.bind_replay_in_a_child(lib); "
                                     "aes_fslib.note_vdi_calls_in_a_child(); ")


def session(machine, interrupts, budget=SESSION_INSNS, arguments=ARGUMENTS, **kwargs):
    """fs_input over `machine` (a replayed one) TAKEN THROUGH `interrupts` on both shores (`aes_event.interrupted`):
    the walked routines served, under the session's declared `budget`."""
    return aes_event.interrupted(INPUT, arguments, machine, interrupts, objects=True, budget=budget, **kwargs)


# ---- THE VDI CALLS A RUN MAKES ---------------------------------------------------------------------------------------------
# What a run DRAWS on its way is gone from the image by its end (the selector gives the screen back; a box grown in XOR
# erases itself; a clip set twice shows the second). So an in-process session's VDI calls are held to the ROM's, call
# for call: the opcode and the input arrays each `trap #2` is made with, read through the AES's own parameter block —
# ours where the candidate's call reaches the hook, the ROM's where its run reaches GEM's trap handler outside any door
# call (the event layer's own keyboard poll is the nested run's on our side, and inside the door on the ROM's).
#
# ...and with each call, WHAT THE SELECTOR HOLDS as it is made (`held`, a hash): its tree's objects, its fields' and
# rows' texts, its two scratches and the two paths it works in. A word of the tree stored between two waits and put
# back before the next — OK shown SELECTED with a bit more, until inf_what clears the whole word at the end — draws
# the same calls and ends on the same image: only the memory at a call in between tells it from the ROM's.
GSX = aes.header_constants("gsx.h")
VDI_TRAP = aes_event.VDI_TRAP
CONTRL_N_PTSIN = GSX["AES_GSX_N_PTSIN"] - GSX["AES_GSX_OPCODE"]     # contrl[1], from contrl[0]
CONTRL_N_INTIN = GSX["AES_GSX_N_INTIN"] - GSX["AES_GSX_OPCODE"]     # contrl[3]
POINT_BYTES = 2 * WORD_BYTES
VdiCall = namedtuple("VdiCall", "opcode intin ptsin held")
HELD_HASH_BYTES = 8


def _selector_spans():
    """`[(address, bytes)]`: the selector's OWN memory — its tree's objects, its two scratches, and the texts of its
    three fields and nine rows."""
    spans = [(SELECTOR, FS["FS_TREE_OBJECTS"] * aes.OB_BYTES), (TEXT, TEXT_ROOM), (NAME, NAME_ROOM)]
    for index in (FS["FS_DIRECTORY"], FS["FS_SELECTION"], FS["FS_TITLE"], *range(FIRST_NAME, FIRST_NAME + ROWS)):
        tedinfo = od.object_long(SELECTOR, index, "SPEC")
        spans.append((aes.read_field(BASE_IMAGE, "TE", "PTEXT", tedinfo), aes.read_field(BASE_IMAGE, "TE", "TXTLEN", tedinfo)))
    return spans


SELECTOR_SPANS = _selector_spans()
# Where the selector keeps what it works on BETWEEN ITS WAITS: its own memory, and the two paths it works in.
HELD_SPANS = [*SELECTOR_SPANS, (aes.AES_RS_STRING, PATH_BYTES), (aes.AES_SH_PATH_BUFFER, PATH_BYTES)]


def held_in(memory):
    """A hash of what the selector holds in `memory` (HELD_SPANS)."""
    hashed = hashlib.blake2b(digest_size=HELD_HASH_BYTES)
    for at, size in HELD_SPANS:
        hashed.update(bytes(memory[at:at + size]))
    return hashed.hexdigest()


def _array(memory, pointer_at, size):
    at = case.long_in(memory, pointer_at) & OS_BUS_ADDR_MASK
    return bytes(memory[at:at + size])


def vdi_call_in(memory):
    """The VDI call `memory` is about to make: its opcode, and the intin and ptsin it hands, through the AES's
    parameter block — and what the selector holds as it makes it (`held_in`)."""
    contrl = case.long_in(memory, GSX["AES_GSX_PB_CONTRL"]) & OS_BUS_ADDR_MASK
    return VdiCall(case.word_in(memory, contrl),
                   _array(memory, GSX["AES_GSX_PB_INTIN"], case.word_in(memory, contrl + CONTRL_N_INTIN) * WORD_BYTES),
                   _array(memory, GSX["AES_GSX_PB_PTSIN"], case.word_in(memory, contrl + CONTRL_N_PTSIN) * POINT_BYTES),
                   held_in(memory))


def _noted_first(effect, note):
    """A door's `effect(buf, ...)` with `note(buf)` taken of the candidate's image before it runs."""
    def noted(buf, *arguments):
        note(buf)
        return effect(buf, *arguments)
    return noted


# THE LEDGER IS THE WHOLE SESSION'S ON BOTH SHORES, wherever the C makes the call. A door call the ROM SERVES runs the
# ROM's event layer on both shores — its VDI traps are the ROM's own, made by no C, and are in neither ledger. A
# REBOUND entry's call runs OUR C on our shore: every VDI function its twin calls (ev_multi's: chkkbd's vq_key_s,
# vsin_mode and vsm_string, mchange's vq_mouse) is a core call of ours like any draw, and the ROM's routine takes the
# same `trap #2` inside its own call. So the ROM's watch keeps the traps taken INSIDE the door calls of the rebound
# entries too, and our ledger notes every VDI function a binding serves (`_noted_functions`: the polled ones with the
# rest, where the poll runs in C) — the count, the order, the arguments and what the selector holds at each, the
# event layer's polls among them. Never "count nothing while a twin runs": that would leave every VDI call the C
# event layer makes under a session held by no ledger at all. Derived from `aes_event.REBOUND`: a flip edits nothing.
def _noted(table, made):
    """`table` (a `{routine: (stub, effect)}` of VDI functions) with each call noted in `made` (a `VdiCall`) before
    its core is run."""
    return {routine: (stub, _noted_first(effect, lambda buf: made.append(vdi_call_in(buf))))
            for routine, (stub, effect) in table.items()}


def _noting_vdi_calls(made):
    """Every VDI function a door user's binding serves IN PROCESS (`aes_event.door_vdi_functions`), each call noted
    in `made`."""
    return _noted(aes_event.door_vdi_functions(), made)


def recording_vdi_hook(made):
    """`aes_gsx.vdi_hook`, every call the candidate makes noted in `made`."""
    return lambda: isr.staged_routines(_noting_vdi_calls(made))


class VdiCalls(aes_event.DoorStops):
    """A watch over the ROM's run — `delivered` laid at its door calls — that stops at GEM's trap handler and keeps
    the VDI call made there (`made`: a `VdiCall` each): outside any door call, and inside the calls of the entries
    `whole` (the REBOUND ones, by default: above). `inside`: the indices in `made` of the calls kept inside a door
    call.

    A stop is taken BEFORE its instruction, and a stop may not arm the PC it stands at: inside a call the handler is
    armed again at the trap's own return (the exception frame's PC), as a marked trap is outside one."""

    def __init__(self, delivered=None, whole=None):
        super().__init__(aes_event.ENTRIES, aes_event.ROM_RETURNS, blocks=True, delivered=delivered)
        self.marked_with(aes_event.Timeline((VDI_TRAP,)))
        self.made, self.inside = [], []
        self._whole = aes_event.REBOUND if whole is None else frozenset(whole)
        self._armed_in_the_call, self._polls_back_at = None, None

    def stopped(self, pc, sp, memory):
        if self.between_calls:
            if pc == VDI_TRAP:
                self.made.append(vdi_call_in(memory))
            armed = super().stopped(pc, sp, memory)
            if self.between_calls or self.entry_at(pc) not in self._whole:
                return armed
            self._armed_in_the_call = armed         # a call of a rebound entry opened: its traps are the ledger's too
            return armed | {VDI_TRAP}
        if self._polls_back_at is None and pc == VDI_TRAP and self._armed_in_the_call is not None:
            self.inside.append(len(self.made))
            self.made.append(vdi_call_in(memory))
            self._polls_back_at = case.long_in(memory, sp + aes_event.EXCEPTION_FRAME_PC)
            return self._armed_in_the_call | {self._polls_back_at}
        if pc == self._polls_back_at:
            self._polls_back_at = None
            return self._armed_in_the_call | {VDI_TRAP}
        self._armed_in_the_call = None
        return super().stopped(pc, sp, memory)


def rom_vdi_calls(machine, budget=None, delivered=None):
    """The VDI calls the ROM's fs_input makes over `machine` in a run that returns — `delivered` laid at its door
    calls — in order."""
    watch = VdiCalls(delivered)
    assert _watched(watch, machine, budget)[0], "the run blocks"
    return watch.made


# ...and IN A CHILD, where a session taken through interrupts runs its C: the child notes each call the same way and
# prints their DIGEST as it exits (a core that returned) — how many, a hash of them all in order, and the opcodes for
# reading a mismatch by.
VDI_CALLS_LINE = "the candidate's VDI calls: "


def digest(calls):
    """`(how many, a hash of every call in order, the opcodes)` of the VDI calls `calls`."""
    hashed = hashlib.sha256()
    for call in calls:
        hashed.update(repr(tuple(call)).encode())
    return len(calls), hashed.hexdigest(), [call.opcode for call in calls]


def note_vdi_calls_in_a_child():
    """In a CHILD, before the event door is bound (`aes_event.declare_child_doors`): the cores `aes_event`'s child
    serves VDI calls from each wrapped to note its call, for this process alone."""
    made = []
    # ...BOTH tables a child's binding may serve from (`aes_event._child_vdi`: the polled functions with the rest
    # where the CHILD's library polls in C, which only its binding knows) — one list, one note per call.
    graphics, with_the_polled = _noted(gsx.vdi_functions(), made), _noted(aes_event.vdi_functions(), made)
    gsx.vdi_functions = lambda: graphics
    aes_event.vdi_functions = lambda: with_the_polled
    atexit.register(lambda: print(VDI_CALLS_LINE + repr(digest(made)), file=sys.stderr))


def vdi_digest_in(stderr):
    """The digest a child of fs_input that returned printed as it exited (`note_vdi_calls_in_a_child`), out of its
    `stderr`."""
    line, = (line for line in stderr.splitlines() if line.startswith(VDI_CALLS_LINE))
    return ast.literal_eval(line.removeprefix(VDI_CALLS_LINE))


def child_vdi_calls(machine, delivered):
    """The digest of the VDI calls fs_input's C makes over `machine` in a child, `delivered` laid at its door calls
    (`aes_event.refusal`: the session's own child, its stderr read)."""
    returncode, stderr, _image = aes_event.door_child(INPUT, ARGUMENTS, machine, objects=True, interrupts=delivered,
                                                      before=aes_event.CHILD_DOORS[INPUT],
                                                      seconds=aes_event.CHILD_RETURN_SECONDS, read_back=False)
    assert returncode == 0, stderr
    return vdi_digest_in(stderr)


def vet_the_draws(ours, machine, delivered, budget):
    """A session's VDI calls on both shores (`machine` a replayed one): `ours` the digest its C's child printed, the
    ROM's off its watched run with the same `delivered` laid — held equal, by the first opcode that differs."""
    the_rom_s = digest(rom_vdi_calls(machine, budget, delivered=delivered))
    assert ours == tuple(the_rom_s), (
        f"fs_input made {ours[0]} VDI calls where the ROM's own run makes {the_rom_s[0]}; the first opcode to differ "
        f"is call {aes_event.first_to_differ(ours[2], the_rom_s[2])} (None: every opcode agrees — an argument "
        f"differs, or what the selector holds at a call)")


def vet_the_draws_of_a_child_of_its_own(machine, interrupts, budget):
    """...the C's in a child run for it — for a session no child has run yet (every child of fs_input prints the
    digest: a session already taken through `session` has it in its `Interrupted.stderr`, and needs no second child)."""
    delivered = aes_event.deliveries(INPUT, ARGUMENTS, machine, interrupts, budget)
    vet_the_draws(child_vdi_calls(machine, delivered), machine, delivered, budget)


# ...and WHAT THE GLUE HAS PARKED at each GEMDOS call: the two return addresses (AES_DOS_RETURN, AES_TRAP1_RETURN) it
# stores before the trap. fs_input frees its three blocks one after the other, each free parking its own site over
# the last one's: the image a run ends on holds the last alone.
def parked_in(memory):
    return case.long_in(memory, aes.AES_DOS_RETURN), case.long_in(memory, aes.AES_TRAP1_RETURN)


def _noting_parks(parked):
    """HANDLERS, each noting in `parked` what the glue has parked when the candidate's call reaches it."""
    return {handler: _noted_first(effect, lambda buf: parked.append(parked_in(buf))) for handler, effect in HANDLERS.items()}


def rom_parks(machine, budget=None):
    """What the ROM's glue has parked at each GEMDOS call fs_input makes over `machine` (a real-disk one), in order."""
    watch = GemdosCalls({}, SESSION_ARGUMENT_BYTES)
    assert _watched(watch, machine, budget)[0], "the run blocks"
    return [parked_in(at_the_call) for _function, _frame, at_the_call in watch.made]


def session_doors(vdi_calls, parked):
    """Every door fs_input's C goes out by IN PROCESS, as one hook: the staged disk and REAL GEMDOS (`doors`: each
    call's parked return addresses noted in `parked`), the VDI — each call noted in `vdi_calls` — and the event door:
    for a session one run can make — its keys typed ahead, or none (no memory: it never waits)."""
    # ...and what the event layer's own C calls out through where an entry that polls is rebound — the polled VDI
    # functions, noted with the rest, and the routines it is handed (`aes_event.door_objects`): the door's standard
    # binding (`aes_event.door_hook`), spelt here because the VDI's half is this session's recorder.
    walked = aes.alcyon_object_hook(aes_event.door_objects(aes.walkers(od.JUST_DRAW)))
    return aes.doors(sh.staged_disk, functools.partial(gemdos.bound_handlers, _noting_parks(parked)),
                     recording_vdi_hook(vdi_calls), walked, aes_event.event_hook())


def gemdos_through(machine, function, *words):
    """`machine` after the ROM's GEMDOS `function`, called by a real `trap #1` with the argument `words` (`_trapped`):
    `(D0, the machine)` — what the call wrote laid over it (`case.written_by`), its own stack out."""
    answer, _final, writes = _trapped(make_image(machine), function, words)
    return answer, merge_pokes(machine, case.written_by(writes))


def continued(machine, memory):
    """`machine` continued by a run of it that left `memory` (its RAM, `ram_in`: all a run changes): every byte the run
    left changed outside the oracle's stack band laid over it — what a SECOND call over the same machine starts from."""
    before, stack = make_image(machine), frozenset(case.STACK_BAND)
    changed = {at: bytes([memory[at]]) for at in aes_event.differing(memory, before, stack)}
    return merge_pokes(machine, changed)


EVERY_BYTE = 0xFFFF_FFFF                # Malloc(-1): how many bytes the largest free block holds


def exhausted(machine, left=0):
    """`machine` with GEMDOS's arena EXHAUSTED as an application exhausts it — by the ROM's own Malloc, block after
    block, until it has none (`gemdos_through`) — but for ONE free block of `left` bytes: the first block taken is
    given back (Mfree) and taken again `left` bytes short. Every Malloc after it finds that block alone."""
    taken = []
    while True:
        largest, machine = gemdos_through(machine, MALLOC, *gemdos.long_words(EVERY_BYTE))
        if not largest:
            break
        block, machine = gemdos_through(machine, MALLOC, *gemdos.long_words(largest))
        assert block, "Malloc refused the block it had just measured"
        taken.append((block, largest))
    if left:
        block, size = taken[0]
        freed, machine = gemdos_through(machine, MFREE, *gemdos.long_words(block))
        assert not freed and size > left, "the arena's first block could not be given back"
        again, machine = gemdos_through(machine, MALLOC, *gemdos.long_words(size - left))
        assert again == block, "Malloc did not take the freed block again"
    return machine


def run_session(machine, budget, **kwargs):
    """fs_input over `machine` (a real-disk one) in ONE run, against its core — REAL GEMDOS and the VDI on both shores
    (`run`'s arrangement), the event layer the ROM's (the event door) — and every frame the C handed the door held to
    the ROM's own, every VDI call it made to the ROM's (`rom_vdi_calls`), the return addresses its glue had parked at
    each GEMDOS call to the ROM's (`rom_parks`). `budget`: the run's cap, declared
    (`aes_event.rom_handed` holds the ROM's run to it both ways) — None for a run inside the oracle's default.
    THE C RUNS FIRST IN A FORK made inside the session's open pass (`aes_event.forked_inside_its_pass`): a core that
    halts or spins fails the case by its own words, never the worker."""
    aes_event.HANDED.clear()
    machine, drawn, parked = merge_pokes(machine, STALE_ANSWERS, STALE_SLOTS), [], []
    result = aes_event.capped_run(INPUT, budget, kwargs, lambda **limits: aes.run_function(
        INPUT, ARGUMENTS, machine, hook=session_doors(drawn, parked), dropped_windows=sh.REAL_WINDOWS, poison=False,
        result=sh.Result, first=aes_event.forked_inside_its_pass(INPUT, ARGUMENTS), **limits))
    _vet_the_parks(parked, rom_parks(machine, budget))
    ours, the_rom_s = list(aes_event.HANDED), aes_event.rom_handed(INPUT, ARGUMENTS, machine, budget=budget)
    assert ours == the_rom_s, f"fs_input handed the door {ours} where the ROM's own run hands {the_rom_s}"
    _vet_the_calls_drawn(drawn, rom_vdi_calls(machine, budget))
    return result


def _vet_the_parks(parked, the_rom_parked):
    """What fs_input's glue had parked at each of its GEMDOS calls is what the ROM's had."""
    assert parked == the_rom_parked, (
        f"at its GEMDOS calls fs_input's glue had parked {[tuple(map(hex, each)) for each in parked]} where the ROM's "
        f"has {[tuple(map(hex, each)) for each in the_rom_parked]}")


def _vet_the_calls_drawn(drawn, the_rom_drew):
    """The VDI calls an in-process run made (`VdiCall`s, whole) are the ROM's, call for call."""
    differ = aes_event.first_to_differ(drawn, the_rom_drew)
    assert differ is None, (
        f"fs_input made {len(drawn)} VDI calls where the ROM's own run makes {len(the_rom_drew)}; the first to differ "
        f"is call {differ}: ours {drawn[differ:differ + 1]}, the ROM's {the_rom_drew[differ:differ + 1]}")
