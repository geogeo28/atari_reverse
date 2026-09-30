"""The RECTANGLE LISTS' staging (`src/aes/rlist.c`, `test_aes_rlist.py`): the ORECT pool, its free list, the window
lists and the cut, as the captured machine holds them and as the ROM's own routines leave them.

THE SNAPSHOT'S POOL is the ROM's own: or_start threaded all 80 ORECTs onto the free list at start-up (the last on top)
and newrect took the top one for the desktop's window — so window 0's list is ORECT 79 alone, the desktop's work area
(0, 11, 320, 189), and the free list runs ORECT 78 down to ORECT 0. Every staged state here is reached from that one
by the ROM's own moves: a SHORTER free list is the head moved down the chain as get_orect moves it (`free_list_of`),
the pool re-threaded is or_start's own run (`after_or_start`), a longer window list is mkrect's own cut of the
snapshot's (`test_aes_rlist.py` chains the runs). The cut itself — gl_mkrect, which newrect sets from w_getsize — and
a window's list head are staged by value.
"""
import sys

from harness import emu, make_image
from recreate_kit.os_map import OS_BUS_ADDR_MASK

import aes
import case
import vdi

# `aes/rlist.h`'s constants — the sides mkpiece's pieces lie on (ORECT_PIECE_*).
sys.modules[__name__].__dict__.update(aes.header_constants("rlist.h"))

OR_START = "AES_ROM_OR_START"
GET_ORECT = "AES_ROM_GET_ORECT"
MKPIECE = "AES_ROM_MKPIECE"
BRKRCT = "AES_ROM_BRKRCT"
MKRECT = "AES_ROM_MKRECT"
aes.declare_alcyon(OR_START, None, (vdi.IMAGE_ARG,))
aes.declare_alcyon(GET_ORECT, aes.LONG_ANSWER, (vdi.IMAGE_ARG,))
aes.declare_alcyon(MKPIECE, aes.LONG_ANSWER, (vdi.IMAGE_ARG, vdi.WORD_ARG, vdi.LONG_ARG, vdi.LONG_ARG))
aes.declare_alcyon(BRKRCT, aes.LONG_ANSWER, (vdi.IMAGE_ARG, vdi.LONG_ARG, vdi.LONG_ARG, vdi.LONG_ARG))
aes.declare_alcyon(MKRECT, None, (vdi.IMAGE_ARG, vdi.LONG_ARG, vdi.WORD_ARG))

POOL_BYTES = aes.AES_ORECT_COUNT * aes.ORECT_BYTES
WINDOWS_BYTES = aes.AES_WINDOW_COUNT * aes.WIN_BYTES
# A NEGATIVE window index reads the 56 bytes below the table (`muls.w #56`, a signed product): window -1's record.
BELOW_WINDOWS = aes.AES_WINDOWS - aes.WIN_BYTES
aes.declare_case_field(aes.AES_ORECT_POOL, POOL_BYTES, "the ORECT pool the rectangle lists are threaded through")
aes.declare_case_field(aes.AES_ORECT_FREE, aes.LONG_BYTES, "the free ORECTs' head")
aes.declare_case_field(aes.AES_GL_MKRECT, aes.ORECT_BYTES, "gl_mkrect, the cut newrect sets")
aes.declare_case_field(BELOW_WINDOWS, aes.WIN_BYTES + WINDOWS_BYTES,
                       "the window records, and window -1's below them (a signed index)")

# ---- the snapshot's pool, named -------------------------------------------------------------------------------------
DESKTOP = 0                                             # window 0: the desktop's, in use, its list one ORECT


def orect(index):
    """The address of ORECT `index` of the pool."""
    return aes.AES_ORECT_POOL + index * aes.ORECT_BYTES


LAST = aes.AES_ORECT_COUNT - 1
DESKTOP_ORECT = orect(LAST)                             # the desktop's one visible rectangle
SNAPSHOT_FREE_HEAD = orect(LAST - 1)                    # ...and the free list, 79 long, ORECT 0 its last


def window_record(window):
    return aes.AES_WINDOWS + window * aes.WIN_BYTES


def list_head(window):
    """The address of window `window`'s list head — the link an ORECT walk starts from."""
    return window_record(window) + aes.WIN_RLIST


# THE ATTRIBUTION PASS IS OFF for the cases of every routine here but or_start that store a link they go on to read
# (`vdi.READS_A_POINTER_IT_WRITES`; `test_aes_rlist.py` keeps it on the rest): the free head, a list's links — and the
# pass, inverting a stored byte before its first read, follows the poisoned pointer into the I/O page. What stands in
# for it: every free ORECT's four words staged STALE (`stale_free_pool`), where the snapshot has zeros, so a piece's
# field the C skipped storing shows.
UNPOISONED = vdi.READS_A_POINTER_IT_WRITES


def stale_free_pool():
    """Every ORECT but the desktop's with its four words stale — its link the snapshot's."""
    return case.merge_pokes(*(aes.field_pokes("ORECT", orect(index), X=aes.STALE_WORD, Y=aes.STALE_WORD,
                                              W=aes.STALE_WORD, H=aes.STALE_WORD) for index in range(LAST)))


def orect_pokes(at, link=None, **words):
    """An ORECT at `at`: its link and any of X, Y, W, H by name."""
    return aes.field_pokes("ORECT", at, **({"LINK": link} if link is not None else {}), **words)


def cut_pokes(x, y, w, h):
    """gl_mkrect, the cut mkrect breaks a window's list by: its four words (its link is never read)."""
    return orect_pokes(aes.AES_GL_MKRECT, X=x, Y=y, W=w, H=h)


def free_list_of(count):
    """The free list as get_orect leaves it after taking all but `count` of the snapshot's: its head moved down the
    chain to the `count`-th ORECT from the end — the links are the snapshot's own. 0 is the exhausted pool."""
    assert 0 <= count <= LAST
    return aes.field_pokes("AES", ORECT_FREE=orect(count - 1) if count else 0)


def rect_of(image, at):
    """An ORECT's four words, signed."""
    return tuple(aes.signed(aes.read_field(image, "ORECT", name, at)) for name in ("X", "Y", "W", "H"))


def walk(image, head, limit=aes.AES_ORECT_COUNT + 1):
    """The ORECT addresses a list links from the link word at `head` (a window's list head, or the free head), each
    followed on the 24-bit bus as the ROM follows it."""
    found, at = [], case.long_in(image, head)
    while at:
        found.append(at)
        assert len(found) <= limit, f"the list at {head:#x} does not end"
        at = case.long_in(image, (at & OS_BUS_ADDR_MASK) + aes.ORECT_LINK)
    return found


def window_rects(image, window):
    return [rect_of(image, at & OS_BUS_ADDR_MASK) for at in walk(image, list_head(window))]


# ---- a machine as a ROM routine's own run leaves it ------------------------------------------------------------------
def after(name, arguments, pokes):
    """The pokes of the machine the ROM's own run of `name` over `pokes` ends in (the oracle alone, `emu.run`) — for a
    registry row, which is built at import; a test chains a real differential instead (`case.continued`)."""
    staged = aes.staged(name, arguments, pokes)
    final, writes, _regs = emu.run(make_image(staged), getattr(aes.addrs, name))
    return case.continued_from(staged, final, writes)


def after_or_start():
    """The machine after the ROM's or_start over the snapshot: the free list all 80, ORECT 79 on top, and window 0's
    list head still naming ORECT 79 — which or_start does not clear, so the desktop's ORECT is on the free list AND
    the window's list, as it is between gem_main's or_start and its newrect."""
    return after(OR_START, (), aes.leaf_machine())


# ---- the model the batteries hold a cut to --------------------------------------------------------------------------
def area(rect):
    x, y, w, h = rect
    return {(column, row) for column in range(x, x + w) for row in range(y, y + h)}


def uncovered(rect, cut):
    """The cells of `rect` the cut does not cover (small, unwrapped rectangles only)."""
    return area(rect) - area(cut)


def pieces_tile(pieces, rect, cut):
    """The pieces are disjoint and cover exactly what the cut leaves of `rect`."""
    cells = [area(piece) for piece in pieces]
    union = set().union(*cells) if cells else set()
    return sum(map(len, cells)) == len(union) and union == uncovered(rect, cut)
