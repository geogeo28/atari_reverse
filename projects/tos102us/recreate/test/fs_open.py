r"""The NAME leaves' staging — what `src/gemdos/fs_open.c`'s batteries share (`sfirst`/`Fsfirst`,
`Dsetpath`, `open`/`Fopen`, `Fattrib`, `Fdelete`).

Every one of them walks a path (`$fc696c`) and searches its last directory (`$fc663c`), so every case
runs over `test/fs_dir.py`'s TREE — the root's eleven shapes, `\SUBDIR\INNER\LEAF` two levels down —
with the path text in that module's band. What this adds:

  * a leaf entered at its own address over the tree (`run`), and the same staging as a Tier 3 row;
  * the root's child list as a whole search would have left it, THREE long, so a walk that reaches
    SUBDIR must cross two sibling links (`walked_root`);
  * the tree with two more root entries that only `Fattrib` needs: a subdirectory with the ARCHIVE
    bit (which, alone of directories, answers the file-only search attribute) and a file whose
    attribute byte has bit 7 set;
  * a DTA full of `SLACK_FILL`, named by the running process.

`Fsfirst` then `Fsnext` is proved as the sequence a program makes through `gemdos_fs.continued`.
"""
import struct

import fs_dir as d
import fs_io as io
import gemdos
import gemdos_fs as fs
import gemdos_process as process

NAME_AT = d.TEXT_AT
DTA_AT = d.DTA_AT
EFILNF = process.GEMDOS_EFILNF
ENHNDL = process.GEMDOS_ENHNDL
EPTHNF = fs.GEMDOS_EPTHNF
EACCDN = fs.GEMDOS_EACCDN
ENMFIL = fs.GEMDOS_ENMFIL


# ---- the root's child list, walked ------------------------------------------------------------------

def walked_root():
    """The root's DNDs as a whole search leaves them — newest first, FULL -> BIG -> SUBDIR — with the
    mark at the end and the end NOT flagged: a path through SUBDIR is found on the list's THIRD link,
    and a walk that searched the disk instead would read the root and flag its end."""
    return {**d.root(child=d.FULL_DND_AT, scanned=d.position_of(d.ROOT_END - 1)),
            **d.full_dnd(sibling=d.BIG_DND_AT), **d.big_dnd(sibling=d.SUBDIR_DND_AT), **d.subdir_dnd()}


# ---- the tree with Fattrib's two extra entries ---------------------------------------------------------
# A subdirectory with the ARCHIVE bit as well, and a file whose attribute byte is negative as a byte —
# both past the tree's own root entries, where its end-of-directory entry was.
ARCHIVED_DIR = "ARCHIVED"
HIGH_BIT_FILE = ("HIGHBIT", "ATR")
HIGH_BIT_ATTR = fs.ATTR_BIT_7 | fs.GEMDOS_ATTR_READ_ONLY     # answers ANY_FILE by its read-only bit
EXTRA_ROOT = [fs.staged_dirent(ARCHIVED_DIR, "", fs.GEMDOS_ATTR_SUBDIR | fs.GEMDOS_ATTR_ARCHIVE),
              fs.staged_dirent(*HIGH_BIT_FILE, HIGH_BIT_ATTR)]
EXTRA_INDEX = {ARCHIVED_DIR: d.ROOT_END, HIGH_BIT_FILE[0]: d.ROOT_END + 1}
ATTRIBUTE_TREE = d.directory_tree(d.ROOT + EXTRA_ROOT, d.DIRECTORIES)


# ---- a DTA ----------------------------------------------------------------------------------------------

def blank_dta():
    """The DTA every search case starts with: `SLACK_FILL` over the whole record and its slack, named
    by the running process."""
    return {DTA_AT: bytes([fs.SLACK_FILL]) * (d.DTA_BYTES + d.DTA_SLACK_BYTES), **gemdos.dta_poke(DTA_AT)}


def dta_name(result):
    """The found name `$fc6ebc` wrote, as text."""
    return result.after(DTA_AT + fs.DTA_NAME, fs.DTA_PATTERN_BYTES + 1).split(b"\0")[0].decode("latin-1")


def dta_long(result, field):
    """One of the DTA's two UNALIGNED longwords, signed."""
    return struct.unpack(">i", result.after(DTA_AT + field, d.LONG_BYTES))[0]


# ---- running a leaf over the tree -------------------------------------------------------------------------

def staging(text, extra=None, tree=d.TREE):
    """`tree` in drive A:, the path `text` in the text band and a blank DTA, then the case's `extra`."""
    return d.staged({**tree, **d.text(text), **blank_dta(), **(extra or {})})


def pokes(leaf, values, text, extra=None, tree=d.TREE):
    """...with `values` as `leaf`'s frame."""
    return fs.leaf_pokes(leaf, values, staging(text, extra, tree))


def run(leaf, values, text, extra=None, tree=d.TREE, buffers=None):
    """`leaf` entered at its own address: `fs_io.run` (the staged drive, an empty cache unless
    `buffers`) over `pokes`."""
    return io.run(leaf.entry, fs.leaf_glue(leaf, values), pokes(leaf, values, text, extra, tree), buffers=buffers)


def register(label, leaf, values, text, extra=None, tree=d.TREE, buffers=None):
    """...and the same staging as a Tier 3 row."""
    return io.register(label, leaf.entry, pokes(leaf, values, text, extra, tree), buffers=buffers)


def dispatch(leaf, words, text, extra=None, tree=d.TREE, buffers=None):
    """...and through the dispatcher: `fs_io.dispatch_slice` with the same staging under it."""
    return io.dispatch_slice(leaf, words, staging(text, extra, tree), buffers=buffers)
