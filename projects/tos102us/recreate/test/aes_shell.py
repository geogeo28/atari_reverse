r"""THE AES's FILE DOORS — what the shell's find (`src/aes/shell_find.c`), the resource load (`src/aes/resource.c`'s
rs_readit/rs_load) and the GEMDOS glue under them (`src/aes/gemdosif.c`) are proved over, on both shores at once.

TWO WAYS TO ANSWER A `trap #1`, and a case picks the one whose surface it needs:

  * REAL GEMDOS over the STAGED RAM DISK (`run_real`, recreate/README.md "A STAGED RAM DISK"): the ROM's glue traps
    into the ROM's GEMDOS, which reaches `test/gemdos_fs.py`'s floppy through its three staged BIOS vectors; our C
    hands the same frame to the reconstructed dispatcher, its handlers bound to the reconstructed leaves
    (`HANDLERS`). The disk holds REAL RESOURCE FILES — the ROM's own resources as its bundle stores them, before any
    relocation — so a load reads a file a GEM program could have shipped, and the relocation the AES makes of it is
    compared byte for byte. Dropped: `vdi_helpers.GEMDOS_DOOR_WINDOWS` (the trap entry's register save, GEMDOS's own
    stack, the termination record — the host build has no trap entry) and the Line-F mask word.
  * A SCRIPTED TRAP (`run_scripted`): the `trap #1` vector pointed at a 68000 handler staged in this module's band
    that RECORDS each call — its function word and its frame — in a ledger and answers the next longword of a
    SCRIPT; the host twin is the same effect over the candidate's image, bound for every function a routine here
    calls. It reaches what a staged disk cannot (a GEMDOS answering a word of 3, a Malloc that fails, a read that
    fails after an open that did not), and it is what Tier 3 prices: real GEMDOS cannot be, because the trap entry's
    register save differs between the shores by nature and a Tier 3 companion compares everything
    (`test_vdi_helpers_gemdos.py` says the same of the VDI's door).

THE LEDGER RECORDS A FRAME AS ITS CALLER PUSHED IT, and the frames are not one shape: the word above Fclose's handle,
or above Fsetdta's or Malloc's longword, is its caller's stack — Alcyon's argument slot on the ROM's side, which no C
build reproduces. So an entry is the function word and TEN bytes — the frame's own, zero-padded — through a 68000
stub that looks each function's frame size up in a table (`FRAME_BYTES`). Ten is dos_read's, the widest: every frame
here is recorded whole, so the ledger pins each target shape (`gemdos/gemdos.h`) completely — a scripted read moves no
data, so its buffer is on the surface through the ledger alone.

NOTHING HERE POISONS. On the real disk for `test/gemdos_fs.py`'s reason (`savptr`, the pool's chain heads, a stored
pointer the ROM follows); on the scripted trap because the handler stores back the ledger's and the script's
pointers, which the attribution pass would invert (`vdi.READS_A_POINTER_IT_WRITES`, the AES dos battery's
precedent). What stands in is staging: every buffer a routine writes starts STALE or FILLed.
"""
import contextlib
import ctypes
import functools
import struct
import types
from collections import namedtuple

from harness import BASE_IMAGE, _lib, addrs

import aes
import aes_resource as rs
import case
import gemdos
import gemdos_fs as fs
import gemdos_process as process
import fs_io as io
import isr
import vdi
import vdi_helpers
from case import merge_pokes
from opcodes import (BCC_W, BRA_S, CLR_W_A0_POSTINC, CMP_W_IMMEDIATE_D0, JMP_PC_INDEX, MOVE_B_PC_INDEX_D0,
                     MOVE_L_A0_POSTINC_D0, MOVE_W_STACK_D0, MOVE_W_STACK_TO_A0_POSTINC, RTE, RTS)
from vdi_helpers import FRAME_WORDS_AT, MOVEA_L_ABSOLUTE_A0, POP_A0, PUSH_A0, STORE_A0_ABSOLUTE

WORD_BYTES = aes.WORD_BYTES
LONG_BYTES = aes.LONG_BYTES

# ---- the routines, and how each is called ------------------------------------------------------------------------
SH_NAME, SH_ENVRN, SH_PATH, SH_FIND = "AES_ROM_SH_NAME", "AES_ROM_SH_ENVRN", "AES_ROM_SH_PATH", "AES_ROM_SH_FIND"
DOS_SFIRST, DOS_OPEN, DOS_READ, DOS_LSEEK = "AES_ROM_DOS_SFIRST", "AES_ROM_DOS_OPEN", "AES_ROM_DOS_READ", "AES_ROM_DOS_LSEEK"
DOS_SDTA, DOS_CLOSE = "AES_ROM_DOS_SDTA", "AES_ROM_DOS_CLOSE"
RS_READIT, RS_LOAD = "AES_ROM_RS_READIT", "AES_ROM_RS_LOAD"
IMAGE, WORD, LONG = vdi.IMAGE_ARG, vdi.WORD_ARG, vdi.LONG_ARG
aes.declare_alcyon(SH_NAME, aes.LONG_ANSWER, (IMAGE, LONG))
aes.declare_alcyon(SH_ENVRN, aes.WORD_ANSWER, (IMAGE, LONG, LONG))
aes.declare_alcyon(SH_PATH, aes.WORD_ANSWER, (IMAGE, WORD, LONG, LONG))
aes.declare_alcyon(SH_FIND, aes.WORD_ANSWER, (IMAGE, LONG, LONG))
aes.declare_alcyon(DOS_SFIRST, aes.WORD_ANSWER, (IMAGE, LONG, WORD))
aes.declare_alcyon(DOS_OPEN, aes.LONG_ANSWER, (IMAGE, LONG, WORD))
aes.declare_alcyon(DOS_READ, aes.LONG_ANSWER, (IMAGE, WORD, WORD, LONG))
aes.declare_alcyon(DOS_LSEEK, aes.LONG_ANSWER, (IMAGE, WORD, WORD, LONG))
# ...and the two that go through $fe3c28, which parks its CALLER's return address — the machine's, carried by no frame:
# the host build is handed it (a host argument, dos_free's precedent).
aes.declare_alcyon(DOS_SDTA, aes.LONG_ANSWER, (IMAGE, LONG, LONG), host_arguments=1)
aes.declare_alcyon(DOS_CLOSE, aes.LONG_ANSWER, (IMAGE, LONG, WORD), host_arguments=1)
aes.declare_alcyon(RS_READIT, aes.WORD_ANSWER, (IMAGE, LONG, LONG))
aes.declare_alcyon(RS_LOAD, aes.WORD_ANSWER, (IMAGE, LONG, LONG))

SHELL = aes.header_constants("shell.h")
GEMDOSIF = aes.header_constants("gemdosif.h")

# The glue's verdict and its parking, staged STALE so a skipped store shows.
DOS_FIELDS = ("DOS_RETURN", "TRAP1_RETURN", "DOS_ERR", "DOS_AX")
STALE_DOS = aes.field_pokes("AES", DOS_RETURN=vdi.STALE_LONG, TRAP1_RETURN=vdi.STALE_LONG, DOS_ERR=aes.STALE_WORD,
                            DOS_AX=aes.STALE_WORD)
TEXT_BYTES = 0x80
# The working path's buffer runs up to the AES's own global[] (rs_str's), which a longer path runs over.
PATH_BUFFER_BYTES = case.long_in(BASE_IMAGE, aes.AES_RS_SYSTEM_GLOBAL) - aes.AES_SH_PATH_BUFFER
SHELL_BUFFER = case.long_in(BASE_IMAGE, aes.AES_SHELL_BUFFER)
for _name in ("SH_PATH_POINTER", "SH_ENVIRONMENT", "SH_SCRATCH", "RS_HEADER_COPY", "DOS_RETURN", "TRAP1_RETURN", "DOS_ERR",
              "DOS_AX", "RS_GLOBAL", "RS_HDR"):
    _field = aes.field("AES", _name)
    aes.declare_case_field(_field.at, _field.width * (_field.count or 1), "the shell's find and the resource load")
aes.declare_case_field(aes.AES_SH_PATH_BUFFER, PATH_BUFFER_BYTES, "the working path's buffer")
aes.declare_case_field(SHELL_BUFFER, aes.AES_SHELL_LINE_BYTES, "the shell's buffer, rs_readit's name")
aes.declare_case_field(addrs.VECTOR_TRAP_GEMDOS, LONG_BYTES, "the trap #1 vector the scripted trap repoints")

# ---- this module's band ---------------------------------------------------------------------------------------------
BAND_OFFSET = 0x1400                            # into the AES's window, clear of `test/aes.py`'s and aes_gsx's bands
BAND_BYTES = 0x300
BAND_AT = aes.SPAN.claim(aes.WINDOW_AT + BAND_OFFSET, BAND_BYTES, "test/aes_shell.py: the scripted trap, names, environments")
SPEC_AT = BAND_AT                               # the spec a case hands sh_find / rs_readit, and room for it to grow
ENVIRONMENT_AT = SPEC_AT + TEXT_BYTES           # a staged environment
ANSWER_AT = ENVIRONMENT_AT + TEXT_BYTES         # a longword sh_envrn answers through, and a routine's log
LOG_AT = ANSWER_AT + LONG_BYTES
ANSWER_AND_LOG_BYTES = 0x10                     # the two longwords, and room
HANDLER_AT = ANSWER_AT + ANSWER_AND_LOG_BYTES   # the scripted trap's handler, then sh_find's two routines
LEDGER_OFFSET = 0x230
LEDGER_AT = BAND_AT + LEDGER_OFFSET             # ...the ledger's pointer, then its entries
SCRIPT_OFFSET = 0x2C0
SCRIPT_AT = BAND_AT + SCRIPT_OFFSET             # ...and the script's pointer, then its answers
LEDGER_ENTRIES = 11
ENTRY_BYTES = 2 * WORD_BYTES + 2 * LONG_BYTES   # the function, then ten bytes of its frame: dos_read's whole
ENTRIES_AT = LEDGER_AT + LONG_BYTES
SCRIPT_ANSWERS = 11
ANSWERS_AT = SCRIPT_AT + LONG_BYTES
assert ENTRIES_AT + LEDGER_ENTRIES * ENTRY_BYTES <= SCRIPT_AT
assert ANSWERS_AT + SCRIPT_ANSWERS * LONG_BYTES <= BAND_AT + BAND_BYTES


def text(at, value, bytes_=TEXT_BYTES):
    """`value` (str or bytes) NUL-ended at `at`, the rest of the buffer FILLed — so a store past it shows."""
    raw = (value.encode("latin-1") if isinstance(value, str) else value) + b"\0"
    assert len(raw) <= bytes_
    return {at: raw + bytes([vdi.FILL]) * (bytes_ - len(raw))}


def spec(value):
    return text(SPEC_AT, value)


def environment(*strings):
    """An environment at ENVIRONMENT_AT — its strings each NUL-ended, then an empty one — and the AES's pointer at it.
    The AES's own is ("PATH=", "A:\\"): the NUL after the `=` is what sh_envrn's copy turns into a `;`."""
    raw = b"".join(s.encode("latin-1") + b"\0" for s in strings)
    return merge_pokes(text(ENVIRONMENT_AT, raw), aes.field_pokes("AES", SH_ENVIRONMENT=ENVIRONMENT_AT))


def working_path(value=""):
    """The working path's buffer (`AES_SH_PATH_BUFFER`) FILLed after `value`."""
    return text(aes.AES_SH_PATH_BUFFER, value, PATH_BUFFER_BYTES)


# ---- (a) REAL GEMDOS over the staged disk -------------------------------------------------------------------------
# THE FILES, on top of `gemdos_fs.DISK`'s six (which keep their clusters 2..6): in the root, the ROM's own AES resource
# (5,052 bytes, every section but ICONBLKs) and the desk's (9,130: ICONBLKs too), each its header's rsh_rssize long, as
# the bundle stores them; in SUBDIR, an application's resource built by shape (`aes_resource.application_resource`),
# which only a PATH element reaches.
GEM_RSC, DESK_RSC, APP_RSC = ("GEM", "RSC"), ("DESK", "RSC"), ("APP", "RSC")
GEM_FILE = rs.rom_bytes(rs.GEM_FRESH_AT, rs.GEM_BYTES)
DESK_FILE = rs.rom_bytes(rs.DESK_FRESH_AT, rs.DESK_BYTES)
(_APP_POKES, APP_LAYOUT) = rs.application_resource(header=0)
APP_FILE = _APP_POKES[0]
# ...and two broken ones a load meets: a header claiming NOTHING (rsh_rssize 0, so the load asks Malloc for 0 bytes)
# and the AES's file CUT short of the length its header claims (a read answers fewer bytes, which is no error).
RSSIZE_AT = aes.RSH_RSSIZE
EMPTY_RSC, CUT_RSC = ("NOTHING", "RSC"), ("CUT", "RSC")
EMPTY_FILE = GEM_FILE[:RSSIZE_AT] + bytes(WORD_BYTES)
CUT_BYTES = 1500
CUT_FILE = GEM_FILE[:CUT_BYTES]
GEM_CLUSTER, DESK_CLUSTER, APP_CLUSTER, EMPTY_CLUSTER, CUT_CLUSTER = 8, 14, 24, 25, 26
SUBDIR_ENTRIES = 2                              # `.` and `..`, then APP.RSC


def _chain(first, contents):
    """`(fat, clusters)` for a file of `contents` from cluster `first` on, its clusters consecutive."""
    count = -(-len(contents) // fs.CLUSTER_BYTES)
    fat = {first + index: first + index + 1 for index in range(count - 1)}
    fat[first + count - 1] = fs.FAT12_END_OF_CHAIN
    clusters = {first + index: contents[index * fs.CLUSTER_BYTES:(index + 1) * fs.CLUSTER_BYTES]
                for index in range(count)}
    return fat, clusters


def _resource_disk():
    fat, clusters = {}, {}
    for first, contents in ((GEM_CLUSTER, GEM_FILE), (DESK_CLUSTER, DESK_FILE), (APP_CLUSTER, APP_FILE),
                            (EMPTY_CLUSTER, EMPTY_FILE), (CUT_CLUSTER, CUT_FILE)):
        more_fat, more_clusters = _chain(first, contents)
        fat.update(more_fat)
        clusters.update(more_clusters)
    clusters[fs.SUBDIR_CLUSTER] = b"".join(fs.dots(fs.SUBDIR_CLUSTER, 0) + [
        fs.staged_dirent(*APP_RSC, cluster=APP_CLUSTER, length=len(APP_FILE))]).ljust(fs.CLUSTER_BYTES, b"\0")
    image = bytearray(fs.disk(fat, clusters)[fs.IMAGE_AT])
    root = [fs.staged_dirent(*row) for row in fs.ROOT_FILES] + [
        fs.staged_dirent(*GEM_RSC, cluster=GEM_CLUSTER, length=len(GEM_FILE)),
        fs.staged_dirent(*DESK_RSC, cluster=DESK_CLUSTER, length=len(DESK_FILE)),
        fs.staged_dirent(*EMPTY_RSC, cluster=EMPTY_CLUSTER, length=len(EMPTY_FILE)),
        fs.staged_dirent(*CUT_RSC, cluster=CUT_CLUSTER, length=len(CUT_FILE))]
    at = fs.ROOT_RECORD * fs.SECTOR_BYTES
    image[at:at + fs.ROOT_SECTORS * fs.SECTOR_BYTES] = b"".join(root).ljust(fs.ROOT_SECTORS * fs.SECTOR_BYTES, b"\0")
    return {fs.IMAGE_AT: bytes(image)}


DISK = _resource_disk()
# The running process's drive A: current directory: node 2 in the capture (the snapshot's own root DND of A:), pointed
# at the staged drive's root.
CURRENT_NODE = BASE_IMAGE[gemdos.BASEPAGE + addrs.BASEPAGE_CURDIR + io.DRIVE]


def disk_machine(pokes=None):
    """The staged drive A: — disk, DMD, empty cache, its root the current directory — then `pokes`."""
    return io.engine(merge_pokes(DISK, fs.dmd_pointer_poke(io.DRIVE),
                                 fs.current_directory_poke(io.DRIVE, CURRENT_NODE, fs.ROOT_DND_AT), pokes))


_lib.gemdos_fsetdta.restype = ctypes.c_uint32


def _fsetdta(buf, arguments, _argument_bytes):
    # Fsetdta answers the dispatcher's own D0 at its `jsr` (`src/gemdos/leaves.c`), which no frame carries and the
    # glue turns into AES_DOS_AX / AES_DOS_ERR; every caller here makes another call before reading either.
    return _lib.gemdos_fsetdta(buf, 0, case.long_in(buf, arguments))


HANDLERS = {
    gemdos.rom_handler(addrs.GEMDOS_FSETDTA_FN): _fsetdta,
    **{gemdos.rom_handler(leaf.selector): fs.leaf_handler(leaf) for leaf in (fs.FSFIRST, fs.FOPEN, fs.FREAD, fs.FSEEK,
                                                                             fs.FCLOSE)},
    **vdi_helpers.GEMDOS_HANDLERS,
}
# The GEMDOS door's windows, its stack's deepened: the file system's frames — a path walk under an Fsfirst, the cache
# under an Fread — run far deeper than the VDI's Malloc and Mfree.
FILE_SYSTEM_STACK_DEPTH = 0x300
_STACK_WINDOWS = [window for window in vdi_helpers.GEMDOS_DOOR_WINDOWS if window[1] == addrs.GEMDOS_SUPERVISOR_STACK]
assert len(_STACK_WINDOWS) == 1, "the GEMDOS door has ONE window on its own stack, the one deepened here"
_STACK_WINDOW = _STACK_WINDOWS[0]
_DEEPENED = (addrs.GEMDOS_SUPERVISOR_STACK - FILE_SYSTEM_STACK_DEPTH, *_STACK_WINDOW[1:])
REAL_WINDOWS = aes.LINE_F_MASK_WINDOW + tuple(_DEEPENED if window == _STACK_WINDOW else window
                                              for window in vdi_helpers.GEMDOS_DOOR_WINDOWS)


class Result(aes.Result, fs.Result):
    """A run read as the AES's records (`aes.Result`) and as the staged disk (`gemdos_fs.Result`)."""


def _hook(doors, routines=None):
    """`doors` (each a zero-argument callable opening its binding) and sh_find's `routines`, if a case stages one
    (`{address: (68000 stub, effect)}`), as ONE `aes.run_function` hook."""
    return aes.doors(*doors, *((aes.alcyon_object_hook(routines),) if routines else ()))


def _run(name, arguments, pokes, *, doors, routines=None, poison=False, **kwargs):
    """`aes.run_function` through `doors` (and `routines`), read as a `Result` — UNPOISONED unless a case says."""
    return aes.run_function(name, arguments, pokes, hook=_hook(doors, routines), poison=poison, result=Result, **kwargs)


# THE TWO FRAMES' HOST SLOTS, staged FILLED: the C keeps sh_envrn's and sh_find's frames there off target, so a local the
# C failed to store reads as fill rather than as whatever the slot held — the stack band, which nothing compares, is
# where the ROM's own frames are too, and they lie elsewhere in it.
DIRTY_FRAMES = merge_pokes(*(aes.stale_host_slot(role, fill=vdi.FILL) for role in ("AES_SH_ENVRN_FRAME", "AES_SH_FIND_FRAME")))
# ...and the ledger's entry is the C's GEMDOS words slot, which the host's trap stages the same frame in.
assert ENTRY_BYTES == aes.HOST_SLOTS["HOST_SLOT_GEMDOS_WORDS_BYTES"]


def run_leaf(name, arguments, pokes=None, **kwargs):
    """`name`, which makes no `trap #1`, over the leaf machine — POISONED; `kwargs` are `aes.run_function`'s (entry
    `regs`: sh_path reads its caller's D6)."""
    return _run(name, arguments, aes.leaf_machine(onto=merge_pokes(DIRTY_FRAMES, pokes)), doors=(), poison=True,
                **kwargs)


@contextlib.contextmanager
def staged_disk():
    """`gemdos_fs.staged_disk`, yielding what opens its passes (`gemdos_fs.recording`), as the other doors do."""
    with fs.staged_disk():
        yield types.SimpleNamespace(recording=fs.recording)


def run_real(name, arguments, pokes=None, **kwargs):
    """`name` over the leaf machine on the staged drive, its `trap #1`s into REAL GEMDOS on both shores; `routines`
    is `{address: (68000 stub, effect)}` for sh_find's routine."""
    machine = fs.machine(disk_machine(aes.leaf_machine(onto=merge_pokes(STALE_DOS, DIRTY_FRAMES, pokes))))
    return _run(name, arguments, machine, doors=(staged_disk, functools.partial(gemdos.bound_handlers, HANDLERS)),
                dropped_windows=REAL_WINDOWS, **kwargs)


# ---- (b) the SCRIPTED TRAP ------------------------------------------------------------------------------------------
# How many bytes of a frame the ledger records, by function: ten — all of Fread's: its handle, count and buffer —
# unless the frame is shorter.
RECORDED_BYTES = ENTRY_BYTES - WORD_BYTES
# Band 5's own seven, then the desk's — band 6's F2 (Dsetdrv, Dsetpath, Dgetdrv, Dgetpath, Fdelete, Fcreate, Mfree)
# and F3 (Fdatime, Dcreate, Ddelete, Fsnext): ruling R8, the table moves once. Dgetdrv and Fsnext push no argument: a
# frame of nothing, the function word alone recorded.
FRAME_BYTES = {addrs.GEMDOS_FCLOSE_FN: WORD_BYTES, addrs.GEMDOS_FSETDTA_FN: LONG_BYTES,
               addrs.GEMDOS_MALLOC_FN: LONG_BYTES, addrs.GEMDOS_FSFIRST_FN: LONG_BYTES + WORD_BYTES,
               addrs.GEMDOS_FOPEN_FN: LONG_BYTES + WORD_BYTES, addrs.GEMDOS_FSEEK_FN: LONG_BYTES + 2 * WORD_BYTES,
               addrs.GEMDOS_FREAD_FN: RECORDED_BYTES,
               addrs.GEMDOS_DGETDRV_FN: 0, addrs.GEMDOS_FSNEXT_FN: 0, addrs.GEMDOS_DSETDRV_FN: WORD_BYTES,
               addrs.GEMDOS_DSETPATH_FN: LONG_BYTES, addrs.GEMDOS_FDELETE_FN: LONG_BYTES, addrs.GEMDOS_MFREE_FN: LONG_BYTES,
               addrs.GEMDOS_DCREATE_FN: LONG_BYTES, addrs.GEMDOS_DDELETE_FN: LONG_BYTES,
               addrs.GEMDOS_DGETPATH_FN: LONG_BYTES + WORD_BYTES, addrs.GEMDOS_FCREATE_FN: LONG_BYTES + WORD_BYTES,
               addrs.GEMDOS_FDATIME_FN: LONG_BYTES + 2 * WORD_BYTES}
SCRIPTED_FUNCTIONS = tuple(FRAME_BYTES)
# The handler's instructions: `move.l a0,-(sp)` puts the trap's frame four bytes up — its SR and PC, then the caller's
# function word (`vdi_helpers.FRAME_WORDS_AT`, the same stub's) and arguments.
ARGUMENTS_IN_FRAME = FRAME_WORDS_AT + WORD_BYTES
BRANCH_BYTES = WORD_BYTES               # a `.s` branch, its displacement in its own word
# The handler looks each function's frame up in a SIZE TABLE — a byte per function word below TOLD_BOUND, the offset
# of the recording block for its frame's size — so every call pays the same dispatch whichever its function, and
# telling one more function moves no other row's cycles (a chain of compares would: each is paid by every function
# behind it). A function word at or past the bound is recorded RECORDED_BYTES deep, as an untold one below it is.
TOLD_BOUND = max(FRAME_BYTES) + 1
assert TOLD_BOUND <= 0x100, "below the bound d0.w's high byte is clear, so the table's byte is the whole index"
FRAME_SIZES = range(0, RECORDED_BYTES + WORD_BYTES, WORD_BYTES)     # a block per size, none to Fread's: widest last
D8_REACH = 0x80                         # an extension word's d8 is a signed byte: forward, at most 0x7f


# ---- THE TWO TABLES OF A RECORDING TRAP HANDLER, spelt once ---------------------------------------------------------------
# Every recording `trap #1` handler the AES's batteries stage walks two tables: the LEDGER it writes each call into (the
# function word, then the frame's own bytes padded with zeros) and the SCRIPT it answers the next call from. Its 68000
# stub is its battery's own (which functions it tells apart, what an answer carries — this file's, and
# `aes_fslib.replay_handler`, whose answers fill a DTA); what both shores share is the tables: how each is staged, how
# the HOST TWIN bounds a pointer before it stores through it, records a call, steps a pointer, and how a run's ledger
# is read back. `vdi_helpers.recording_trap_handler` is not on it: one fixed entry shape at a ledger with no script.
class Table(namedtuple("Table", "pointer_at entries stride what")):
    """One table of a recording handler: a longword at `pointer_at` naming the next of `entries` entries of `stride`
    bytes, the first right after the pointer; `what` it is called in a refusal."""

    @property
    def first(self):
        return self.pointer_at + LONG_BYTES

    def staged(self, content=b""):
        """The table as a run starts on it: its pointer at its first entry, `content`, then FILL to its end."""
        assert len(content) <= self.entries * self.stride, f"the {self.what} holds {self.entries} entries: too few"
        return {self.pointer_at: struct.pack(">I", self.first) + content.ljust(self.entries * self.stride, bytes([vdi.FILL]))}

    def next(self, buf):
        """The entry the pointer in the candidate's image `buf` names, held INSIDE the table and ON an entry first:
        `buf` is a C pointer the twin stores through, and past the table the 68000 handler would run on over the band."""
        pointer = case.long_in(buf, self.pointer_at)
        self._index(pointer, self.entries - 1, "the twin refuses it")
        return pointer

    def _index(self, pointer, most, refused):
        """Which entry `pointer` names, from 0 to `most` — refused by name (`refused`: what is then not done) where it
        is outside those, or between two of them."""
        index, spare = divmod(pointer - self.first, self.stride)
        assert self.first <= pointer <= self.first + most * self.stride, (
            f"the {self.what}'s pointer {pointer:#x} is outside it: {refused}")
        assert not spare, f"the {self.what}'s pointer {pointer:#x} is between two of its entries: {refused}"
        return index

    def step(self, buf, entry):
        """The pointer stored back, one entry past `entry`."""
        isr.poke(buf, self.pointer_at, struct.pack(">I", entry + self.stride))

    def record(self, buf, entry, function, arguments, frame_bytes):
        """A LEDGER's entry at `entry`: `function`, then `frame_bytes` of the frame at `arguments` (an offset into
        `buf`), zero-padded — and the pointer stepped. The padded frame."""
        frame = ctypes.string_at(ctypes.addressof(buf.contents) + arguments, frame_bytes).ljust(self.stride - WORD_BYTES,
                                                                                               b"\0")
        isr.poke(buf, entry, struct.pack(">H", function) + frame)
        self.step(buf, entry)
        return frame

    def recorded(self, image):
        """A LEDGER read back from a run's `image`: `[(function, frame bytes), ...]`, in the order of the calls."""
        count = self._index(case.long_in(image, self.pointer_at), self.entries, "no ledger can be read off it")
        entries = (self.first + index * self.stride for index in range(count))
        return [(case.word_in(image, at), bytes(image[at + WORD_BYTES:at + self.stride])) for at in entries]

    def frame(self, *fields):
        """A LEDGER entry's frame bytes for fields given as ('w', value) / ('l', value), zero-padded as recorded."""
        raw = b"".join(struct.pack(">H" if kind == "w" else ">I", value & (0xFFFF if kind == "w" else 0xFFFF_FFFF))
                       for kind, value in fields)
        recorded = self.stride - WORD_BYTES
        return raw[:recorded].ljust(recorded, b"\0")


LEDGER = Table(LEDGER_AT, LEDGER_ENTRIES, ENTRY_BYTES, "ledger")
SCRIPT = Table(SCRIPT_AT, SCRIPT_ANSWERS, LONG_BYTES, "script")
assert (LEDGER.first, SCRIPT.first) == (ENTRIES_AT, ANSWERS_AT)


# ---- EVERY RECORDING TRAP OF GEMDOS'S, KNOWN BY ITS HANDLER (band 6 W3a stage 1's fix pass): what the class "a frame
# address handed to GEMDOS" is read off (`aes_switching.frame_addresses_handed`, the user's ruling of 2026-10-25) ----
# A recording `trap #1` of the tree — this module's scripted trap, an `aes_gemdosif.Recorder`, `aes_fslib`'s replay —
# is known where a run stands BY ITS HANDLER'S OWN BYTES at the address the GEMDOS vector names: `at` the handler,
# `handler` its bytes, `ledger` the `Table` it records each call in (the function word, then the frame's own bytes),
# `frame_bytes` `{function: how many bytes of its frame are its own}` and `recorded_bytes` how many an entry holds for
# any other function (past a frame's own bytes an entry is zeros), `dta_cell` where it keeps the DTA an Fsetdta named
# (None: it keeps none), `pointer_offsets` where in each function's recorded frame a POINTER it was handed lies
# (POINTER_ARGUMENTS, less a function whose recorder records something else there). Registered as each recorder is
# made, by a callable that answers it (laid out on demand).
#
# POINTER_ARGUMENTS: `{function: the offsets of its pointer arguments into its frame}`, each read off the GEMDOS
# binding it records (the frame's arguments in the order pushed, the function word not counted). A function absent —
# Malloc's amount, Fclose's handle, Fseek, Dsetdrv, Dgetdrv, Fsnext, Cconout, Crawio — is handed no pointer: a count, a
# handle, a mode, an attribute or a date is never read as an address (review RS1F's G1).
POINTER_ARGUMENTS = {
    addrs.GEMDOS_FSETDTA_FN: (0,),          # Fsetdta(dta.l)
    addrs.GEMDOS_FSFIRST_FN: (0,),          # Fsfirst(filespec.l, attr.w)
    addrs.GEMDOS_DFREE_FN: (0,),            # Dfree(buf.l, drive.w)
    addrs.GEMDOS_FOPEN_FN: (0,),            # Fopen(name.l, mode.w)
    addrs.GEMDOS_FCREATE_FN: (0,),          # Fcreate(name.l, attr.w)
    addrs.GEMDOS_FDELETE_FN: (0,),          # Fdelete(name.l)
    addrs.GEMDOS_FATTRIB_FN: (0,),          # Fattrib(name.l, wflag.w, attr.w)
    addrs.GEMDOS_FDATIME_FN: (0,),          # Fdatime(timeptr.l, handle.w, wflag.w)
    addrs.GEMDOS_DCREATE_FN: (0,),          # Dcreate(path.l)
    addrs.GEMDOS_DDELETE_FN: (0,),          # Ddelete(path.l)
    addrs.GEMDOS_DSETPATH_FN: (0,),         # Dsetpath(path.l)
    addrs.GEMDOS_DGETPATH_FN: (0,),         # Dgetpath(buf.l, drive.w)
    addrs.GEMDOS_MFREE_FN: (0,),            # Mfree(block.l)
    addrs.GEMDOS_FREAD_FN: (6,),            # Fread(handle.w, count.l, buf.l)
    addrs.GEMDOS_FWRITE_FN: (6,),           # Fwrite(handle.w, count.l, buf.l)
    addrs.GEMDOS_FRENAME_FN: (2, 6),        # Frename(zero.w, oldname.l, newname.l)
    addrs.GEMDOS_MSHRINK_FN: (2,),          # Mshrink(zero.w, block.l, newsize.l)
    addrs.GEMDOS_PEXEC_FN: (2, 6, 10),      # Pexec(mode.w, name.l, tail.l, env.l)
}
GemdosLedger = namedtuple("GemdosLedger", "at handler ledger frame_bytes recorded_bytes dta_cell pointer_offsets",
                          defaults=(POINTER_ARGUMENTS,))
GEMDOS_LEDGERS = []


def gemdos_ledger_of(image):
    """The `GemdosLedger` of `GEMDOS_LEDGERS` whose handler the GEMDOS vector of `image` names, its bytes there — None
    where no recorder of the tree's stands there."""
    at = case.long_in(image, addrs.VECTOR_TRAP_GEMDOS) & aes.OS_BUS_ADDR_MASK
    found = (ledger for ledger in (made() for made in GEMDOS_LEDGERS)
             if ledger.at == at and bytes(image[at:at + len(ledger.handler)]) == ledger.handler)
    return next(found, None)


def laid_out(pieces):
    """68000 bytes out of `pieces`: bytes, ("label", name), or (branch opcode, label) — a `.s` branch, resolved."""
    at, labels = 0, {}
    for piece in pieces:
        if isinstance(piece, bytes):
            at += len(piece)
        elif piece[0] == "label":
            labels[piece[1]] = at
        else:
            at += BRANCH_BYTES
    code, at = b"", 0
    for piece in pieces:
        if isinstance(piece, bytes):
            code, at = code + piece, at + len(piece)
        elif piece[0] != "label":
            opcode, label = piece
            displacement = labels[label] - (at + BRANCH_BYTES)
            assert 0 < displacement < 0x80
            code, at = code + vdi.pack_words(opcode << 8 | displacement), at + BRANCH_BYTES
    return code


def _recording_block(size):
    """A frame of `size` bytes into the ledger: its words, then the zeros that pad its entry to RECORDED_BYTES."""
    words = [vdi.pack_words(MOVE_W_STACK_TO_A0_POSTINC, ARGUMENTS_IN_FRAME + at) for at in range(0, size, WORD_BYTES)]
    return b"".join(words) + vdi.pack_words(CLR_W_A0_POSTINC) * ((RECORDED_BYTES - size) // WORD_BYTES)


def _recording_blocks():
    """A block per frame size, the shortest first, each but the widest ending in a `bra.s` to what follows them all —
    the widest, laid last, falls into it: `{size: its block's offset}`, and the blocks laid."""
    offsets, at, pieces = {}, 0, []
    for size in FRAME_SIZES:
        block = _recording_block(size)
        offsets[size], at = at, at + len(block)
        pieces.append(block)
        if size != RECORDED_BYTES:
            pieces.append((BRA_S, "recorded"))
            at += BRANCH_BYTES
    return offsets, laid_out(pieces + [("label", "recorded")])


def _d8(displacement):
    """A brief extension word with d0.w as its index: its d8 alone, reaching forward."""
    assert 0 < displacement < D8_REACH
    return displacement


# NOT `vdi_helpers.recording_trap_handler`, which this cannot extend: that one records one shape, (function, longword),
# at a fixed ledger the VDI's batteries share, and answers one fixed value; the AES's and the desk's glue trap with
# six frame shapes (none, a word, a longword, a longword and a word, a longword and two words, Fread's ten bytes),
# each recorded whole, and a load needs a different answer per call — the SCRIPT. Nor `aes_gemdosif.Recorder`'s
# chain of compares, whose cost grows with every function told (TOLD_BOUND).
def handler_stub():
    """The recording handler: the function word into the ledger; below TOLD_BOUND, its frame's block looked up in the
    size table (`move.b`) and jumped to (`jmp`), at or past it (`bcc.w`) the widest block; the block's frame words and
    pads; the ledger's pointer stored back; D0 the script's next longword, its pointer stored back; `rte`. Every
    register but D0 as found."""
    offsets, blocks = _recording_blocks()
    table = bytes(offsets[FRAME_BYTES.get(function, RECORDED_BYTES)] for function in range(TOLD_BOUND))
    table += bytes(len(table) % WORD_BYTES)                     # the blocks start on a word
    head = PUSH_A0 + MOVEA_L_ABSOLUTE_A0 + struct.pack(">I", LEDGER_AT) + vdi.pack_words(
        MOVE_W_STACK_TO_A0_POSTINC, FRAME_WORDS_AT, MOVE_W_STACK_D0, FRAME_WORDS_AT, CMP_W_IMMEDIATE_D0, TOLD_BOUND)
    # bcc.w, move.b, jmp: each an opcode word, then the word its PC-relative operand counts from
    branch_from = len(head) + WORD_BYTES
    table_from = branch_from + 2 * WORD_BYTES
    jump_from = table_from + 2 * WORD_BYTES
    table_at = jump_from + WORD_BYTES
    blocks_at = table_at + len(table)
    dispatch = vdi.pack_words(BCC_W, blocks_at + offsets[RECORDED_BYTES] - branch_from,
                              MOVE_B_PC_INDEX_D0, _d8(table_at - table_from), JMP_PC_INDEX, _d8(blocks_at - jump_from))
    tail = (STORE_A0_ABSOLUTE + struct.pack(">I", LEDGER_AT) + MOVEA_L_ABSOLUTE_A0 + struct.pack(">I", SCRIPT_AT)
            + vdi.pack_words(MOVE_L_A0_POSTINC_D0) + STORE_A0_ABSOLUTE + struct.pack(">I", SCRIPT_AT) + POP_A0 + RTE)
    return head + dispatch + table + blocks + tail


GEMDOS_LEDGERS.append(lambda: GemdosLedger(HANDLER_AT, handler_stub(), LEDGER, FRAME_BYTES, RECORDED_BYTES, None))
ROUTINE_AT = HANDLER_AT + len(handler_stub())
# sh_find's ROUTINE: a LOGGER storing the longword it is called over at LOG_AT, and a SETTER that does that and sets
# AES_DOS_ERR, which sh_find reads AFTER the call.
LOGGER, _logged = isr.frame_long_logger(LOG_AT)
SETTER = isr.store_frame_long(LOG_AT) + isr.store_word(1, aes.AES_DOS_ERR) + RTS
SETTER_AT = ROUTINE_AT + len(LOGGER)
assert SETTER_AT + len(SETTER) <= LEDGER_AT


def _set_dos_err(buf, registers):
    _logged(buf, registers)
    isr.poke(buf, aes.AES_DOS_ERR, struct.pack(">H", 1))


ROUTINES = {"logger": {ROUTINE_AT: (LOGGER, _logged)}, "setter": {SETTER_AT: (SETTER, _set_dos_err)}}
STALE_LOG = {LOG_AT: struct.pack(">I", vdi.STALE_LONG)}


def routine_at(which):
    """Where sh_find's routine `which` is staged: the longword a case hands sh_find."""
    (at,) = ROUTINES[which]
    return at


def routine_pokes(which):
    """sh_find's routine `which`, staged with its log STALE."""
    code, _effect = ROUTINES[which][routine_at(which)]
    return merge_pokes({routine_at(which): code}, STALE_LOG)


def scripted_pokes(answers):
    """The trap vector at the handler, an empty ledger (its entries FILLed) and the script of `answers`."""
    script = b"".join(struct.pack(">I", answer & 0xFFFF_FFFF) for answer in answers)
    return {addrs.VECTOR_TRAP_GEMDOS: struct.pack(">I", HANDLER_AT), HANDLER_AT: handler_stub(),
            **LEDGER.staged(), **SCRIPT.staged(script)}


def _scripted(function):
    """The handler's HOST TWIN for `function`: the same ledger entry, the same answer, both pointers bounded."""
    def handler(buf, arguments, _argument_bytes):
        entry, answer_at = LEDGER.next(buf), SCRIPT.next(buf)
        LEDGER.record(buf, entry, function, arguments, FRAME_BYTES[function])
        SCRIPT.step(buf, answer_at)
        return case.long_in(buf, answer_at)
    return handler


SCRIPTED_HANDLERS = {gemdos.rom_handler(function): _scripted(function) for function in SCRIPTED_FUNCTIONS}


def scripted_hook():
    """The host twin bound as `aes.run_function`'s / `aes.register`'s `hook`."""
    return gemdos.bound_handlers(SCRIPTED_HANDLERS)


def scripted_hook_with(which):
    """...and with sh_find's routine `which` bound too (`ROUTINES`): a `hook` for a row that calls it."""
    return _hook((scripted_hook,), ROUTINES[which])


def calls(image):
    """The ledger in `image` as `[(function, frame bytes), ...]`, in the order the calls were made."""
    return LEDGER.recorded(image)


def frame(*fields):
    """A ledger entry's frame bytes for fields given as ('w', value) / ('l', value), zero-padded to RECORDED_BYTES."""
    return LEDGER.frame(*fields)


# THE HOST'S TRAP REACHES THE RECONSTRUCTED DISPATCHER, which RESOLVES a file handle before it calls Fread's or Fseek's
# handler (`src/gemdos/dispatch.c`, $fc9924) and answers EIHNDL for one naming nothing; on the ROM's side the scripted
# handler stands in for the whole of GEMDOS, dispatcher included. So the handle a script's Fopen answers is staged
# OPEN — a descriptor naming a stand-in the twin never reads — for the host's resolution to pass, and the ROM's side
# reads it not at all (the table is compared, and nothing on either side writes it).
SCRIPTED_HANDLE = addrs.GEMDOS_FIRST_FILE_HANDLE
OPEN_FOR_THE_HOST = process.descriptor_poke(SCRIPTED_HANDLE, BAND_AT, gemdos.BASEPAGE)


def scripted_machine(answers, pokes=None):
    return aes.leaf_machine(onto=merge_pokes(STALE_DOS, OPEN_FOR_THE_HOST, DIRTY_FRAMES, scripted_pokes(answers), pokes))


def run_scripted(name, arguments, answers, pokes=None, **kwargs):
    """`name` over the leaf machine with every `trap #1` answered by the script of `answers` (`routines`: `run_real`'s)."""
    return _run(name, arguments, scripted_machine(answers, pokes), doors=(scripted_hook,), **kwargs)


# ---- a HALT, in a child process --------------------------------------------------------------------------------------
# The child's GEMDOS handler hook bound to a callback answering 0, so a core that traps before it halts reaches its halt.
NULL_GEMDOS = ("answer_0 = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, "
               "ctypes.c_uint16)(lambda *_: 0); "
               "ctypes.c_void_p.in_dll(lib, 'recreate_call_gemdos_handler').value = "
               "ctypes.cast(answer_0, ctypes.c_void_p).value")


def refusal_with_a_null_gemdos(symbol, pokes, arguments):
    """`vdi_helpers.refusal_over` of the core `symbol(image, *arguments)` (longwords) over the image `pokes` stage, its
    GEMDOS answered by `NULL_GEMDOS`. Answers `(returncode, stderr)`."""
    returncode, stderr, _image = vdi_helpers.refusal_over(
        symbol, pokes, arguments=tuple(("ctypes.c_uint32", hex(value)) for value in arguments), read_back=False,
        bind=NULL_GEMDOS)
    return returncode, stderr
