"""The GEMDOS memory group's case shape: the pool as the snapshot holds it, and how a case re-cuts it.

Four batteries share this — `test_gemdos_memory_pool.py`, `..._malloc.py`, `..._mfree.py` and
`..._mshrink.py`. What it owns is the three things all of them need and none of them should spell
twice: the ADDRESSES (read out of `include/gemdos_memory.h`, so a case and the core it proves cannot
disagree), a READER for the two lists and the record pool, and a STAGER that puts the machine into a
pool state the case wants.

WHAT A STAGED POOL MAY BE. The rule these batteries hold to is that every state a case starts from
is one the ROM's own code could have produced, because a differential over an impossible machine
proves nothing about the real one. In practice that is a strong constraint and a simple one:

  * every descriptor is an 18-byte record cut from the bump arena at `$2a6e`, with the size-class
    word 1 below it and the arena's two counters moved by the nine words it cost — which is exactly
    what `gemdos_pool_get` leaves behind, and what makes `arena_cursor` below a re-implementation of
    the ROM's bump rather than a convenient fiction;
  * the descriptors a case adds come from RE-CUTTING THE SNAPSHOT'S OWN FREE BLOCK, the one
    16-byte descriptor at `$2d54` spanning `$1dde2..$f8000`. Its first piece keeps that descriptor,
    exactly as a `Malloc` split does, and the pieces are laid in ADDRESS ORDER because the free list
    is sorted and `gemdos_md_free_insert` is the only thing that ever adds to it;
  * the desktop's own fourteen allocated descriptors are left ON the allocated list, below whatever
    the case pushes in front of them. Nothing is orphaned, and every byte from `_membot` to
    `_memtop` stays accounted for by exactly one descriptor — which
    `test_gemdos_memory_pool.py::test_the_two_lists_tile_the_tpa_with_no_gap_and_no_overlap` holds
    both the snapshot and every staged pool to.

WHY NOTHING HERE POISONS. `case.run`'s attribution pass pre-inverts every byte the oracle wrote and
re-runs BOTH cores. These routines chase the pointers they write — `mp_mfl` is read by
`gemdos_md_free_insert` and written by it, `mp_rover` is read by `gemdos_md_alloc` and written by it
— so an inverted list head is followed, on both sides, into `$ffffd2ab`: the ORACLE decodes that as
the I/O page and the run is refused for reading an unmodelled byte, while the candidate reads image
bytes there. The pass would fail for a reason that is about the pass. `assert_every_store_moved_a_byte`
below is what these batteries use instead, and it is stronger for this group than poison is: it
requires of EVERY case that every longword the routine stored differs from what the field held on
entry, so a candidate that skipped any one of them reddens in the ordinary byte compare. A store
that cannot be made visible has to be named, with its reason, in the case's own `settled` list.
"""
import struct
import sys
from collections import namedtuple
from pathlib import Path

from harness import BASE_IMAGE, addrs, emu, in_diff, make_image

import case

# ---- the addresses, out of the C header that defines them ---------------------------------------
# `tools/addrs.py` binds `include/addrs.h` and is reached THROUGH `harness` (the shim is what puts
# the project's own tools on `sys.path`). This group's own constants live in
# `include/gemdos_memory.h` — the wave's ownership rule is one header per subsystem — so they are
# parsed out of it by that same parser and bound here. One source of truth, one parser, two headers.
GEMDOS_MEMORY_HEADER = Path(__file__).resolve().parents[1] / "include" / "gemdos_memory.h"
CONSTANTS = addrs.parse(GEMDOS_MEMORY_HEADER)
sys.modules[__name__].__dict__.update(CONSTANTS)

# THE ROUTINE ADDRESSES ARE `addrs.h`'S, not this header's. `include/gemdos_memory.h` holds the
# STRUCTURES the cores compile against; an entry point is something the REGISTRIES key on — the
# dispatch-table pin pairs every `<NAME>`/`<NAME>_FN` it finds there against the ROM's own table, and
# `bench/tier3.py` labels a row by the same pair — so the eight live in `addrs.h` with every other
# routine's and are reached through `addrs` here.

# One descriptor costs this much of the arena: the sixteen bytes of the record plus the class word
# below it, which `gemdos_pool_get` asks for as `class * 8 + 1` WORDS.
MD_ARENA_WORDS = MD_SIZE_CLASS * (1 << POOL_CLASS_WORDS_SHIFT) + 1
MD_ARENA_BYTES = MD_ARENA_WORDS * 2

# ...and the class a basepage is, which is the other size the ROM is known to ask for: GEMDOS's init
# allocates the root process's 256-byte basepage with `pool_get(16)` at $fc9376.
BASEPAGE_SIZE_CLASS = 16


# ---- reading the pool out of an image ------------------------------------------------------------

Descriptor = namedtuple("Descriptor", "at link start length owner")


def descriptor(image, at):
    """The four fields of the memory descriptor at `at`."""
    return Descriptor(at,
                      case.long_in(image, at + addrs.MD_LINK),
                      case.long_in(image, at + addrs.MD_START),
                      case.long_in(image, at + addrs.MD_LENGTH),
                      case.long_in(image, at + addrs.MD_OWNER))


# A pool walk is bounded so that a corrupt or circular list fails as a named assertion rather than
# as a hung test. Nothing the ROM builds comes near it: the snapshot holds fifteen descriptors in
# all and the arena has room for 888.
MAX_DESCRIPTORS = 2000


def chain(image, head_address):
    """Every descriptor on the list whose head longword is at `head_address`, in list order."""
    out = []
    at = case.long_in(image, head_address)
    while at != 0:
        assert len(out) < MAX_DESCRIPTORS, (
            f"the list at {head_address:#x} has more than {MAX_DESCRIPTORS} descriptors on it, so "
            f"it is circular — the staged pool is not a shape the ROM could have produced")
        out.append(descriptor(image, at))
        at = out[-1].link
    return out


def free_list(image=None):
    return chain(BASE_IMAGE if image is None else image, GEMDOS_MPB + addrs.MPB_FREE_LIST)


def allocated_list(image=None):
    return chain(BASE_IMAGE if image is None else image,
                 GEMDOS_MPB + addrs.MPB_ALLOCATED_LIST)


def rover(image=None):
    return case.long_in(BASE_IMAGE if image is None else image, GEMDOS_MPB + addrs.MPB_ROVER)


def recycled_descriptors(image=None):
    """The class-1 free chain at `p_root[1]` — the descriptors `gemdos_pool_free` has given back."""
    image = BASE_IMAGE if image is None else image
    out = []
    at = case.long_in(image, GEMDOS_P_ROOT + MD_SIZE_CLASS * POOL_CHAIN_ENTRY_BYTES)
    while at != 0:
        assert len(out) < MAX_DESCRIPTORS, "the class-1 free chain is circular"
        out.append(at)
        at = case.long_in(image, at)
    return out


def size_class_of(image, record):
    """The class word the pool wrote below `record` — what `gemdos_pool_free` reads to file it."""
    return case.word_in(image, record - POOL_CLASS_HEADER_BYTES)


def arena_used_words(image=None):
    return case.word_in(BASE_IMAGE if image is None else image, GEMDOS_POOL_USED_WORDS)


def arena_free_words(image=None):
    return case.word_in(BASE_IMAGE if image is None else image, GEMDOS_POOL_FREE_WORDS)


def arena_cursor(image=None):
    """Where `gemdos_pool_arena_alloc` would put the NEXT record: the ROM's own bump arithmetic."""
    return GEMDOS_POOL_ARENA + arena_used_words(image) * 2


# ---- staging a pool ------------------------------------------------------------------------------

# The snapshot's whole free list is ONE descriptor over the top of the TPA. Both are read rather than
# written down: a future capture with a different desktop moves them, and a case built on a constant
# would then be staging over live data.
SNAPSHOT_FREE_MD = None          # bound below, once BASE_IMAGE can be walked

# The length a recycled descriptor is staged holding, so that the clear moves bytes (see
# `stage`). Any nonzero value does; this one is a round block size the machine really uses.
STALE_DESCRIPTOR_LENGTH = 0x100

FREE = "free"                    # a span that stays on the FREE list
USED = "used"                    # ...and one the case wants on the ALLOCATED list


def fill(*spans):
    """`spans` in address order, with a final FREE span taking whatever is left of the block.

    Every stager call has to account for the whole block (see `stage`), and writing the remainder
    out by hand in each case would be one subtraction per case to get wrong.
    """
    rest = SNAPSHOT_FREE_MD.length - sum(length for _kind, length in spans)
    assert rest > 0, "the spans already fill the block — say so with a plain list instead"
    return list(spans) + [(FREE, rest)]


def _snapshot_free_descriptor():
    blocks = free_list()
    assert len(blocks) == 1, (
        f"the snapshot's free list holds {len(blocks)} descriptors, not the one every stager here "
        f"re-cuts — the capture has changed and these batteries need re-reading, not re-pointing")
    return blocks[0]


SNAPSHOT_FREE_MD = _snapshot_free_descriptor()


class _Arena:
    """The bump arena, re-played the way `gemdos_pool_arena_alloc` plays it, to cut staged records.

    A stager cuts descriptors here rather than picking dead addresses, so the counters it leaves are
    the ones the ROM would have left — which matters because the routines under test READ them: the
    first split a case's `Malloc` makes takes the next record from exactly this cursor.
    """

    def __init__(self):
        self.used = arena_used_words()
        self.left = arena_free_words()
        self.pokes = {}

    def _cursor(self):
        return GEMDOS_POOL_ARENA + self.used * 2

    def descriptor(self):
        record = self._cursor()
        assert MD_ARENA_WORDS <= self.left, (
            "the staged pool asks for more descriptors than the arena has room for")
        self.used += MD_ARENA_WORDS
        self.left -= MD_ARENA_WORDS
        self.pokes[record] = struct.pack(">H", MD_SIZE_CLASS)
        return record + POOL_CLASS_HEADER_BYTES

    def next_record(self):
        """Where the NEXT `gemdos_pool_get` would cut a descriptor, once this staging is in place —
        which is what a case naming the remainder of a split has to say. Not `arena_cursor()`: that
        reads the snapshot, and the staging has already bumped past it."""
        return self._cursor() + POOL_CLASS_HEADER_BYTES

    def counters(self):
        return {GEMDOS_POOL_USED_WORDS: struct.pack(">H", self.used),
                GEMDOS_POOL_FREE_WORDS: struct.pack(">H", self.left)}


def _descriptor_poke(at, link, start, length, owner):
    return {at: struct.pack(">IIII", link, start, length, owner)}


Staged = namedtuple("Staged", "pokes spans free used rover recycled next_md")
Span = namedtuple("Span", "kind md start length")


def stage(spans, rover_span=0, recycled=0, arena_words_left=None):
    """Re-cut the snapshot's one free block into `spans`, as `(kind, length)` pairs in ADDRESS order.

    `kind` is `FREE` or `USED`; the lengths must sum to the block's own, so the TPA stays tiled. The
    FIRST span keeps the snapshot's own descriptor (a `Malloc` split leaves the original descriptor
    on the piece at the low end) and every later one is cut from the arena. `USED` spans are pushed
    onto the head of the allocated list in the order given, above the desktop's own fourteen, and
    owned by the process `p_run` names — which is what `gemdos_md_alloc` does to a block it hands
    out.

    `rover_span` is the index into the FREE spans of the one the rover sits on (the ROM leaves it
    on a descriptor, never on the MPB), or `None` for the empty-free-list state. `recycled` is how
    many spare descriptors to put on the class-1 free chain, which is the state `gemdos_pool_free`
    leaves and the one that makes a split cost no arena. `arena_words_left` overrides the counter that says how much arena is left —
    the one input that makes the descriptor pool RUN OUT, and a word the ROM writes itself.

    Returns a `Staged`: the pokes, the spans with the descriptor each one got, and `next_md` —
    where the next `gemdos_pool_get` will cut, which is what names the remainder of a split.
    """
    total = sum(length for _kind, length in spans)
    assert total == SNAPSHOT_FREE_MD.length, (
        f"the spans sum to {total:#x}, not the {SNAPSHOT_FREE_MD.length:#x} of the block they "
        f"re-cut — a staged pool that loses or invents bytes is not a pool the ROM could produce")

    arena = _Arena()
    laid, start = [], SNAPSHOT_FREE_MD.start
    for index, (kind, length) in enumerate(spans):
        md = SNAPSHOT_FREE_MD.at if index == 0 else arena.descriptor()
        laid.append(Span(kind, md, start, length))
        start += length
    spare = [arena.descriptor() for _ in range(recycled)]

    free = [span for span in laid if span.kind == FREE]
    used = [span for span in laid if span.kind == USED]
    # AN EMPTY FREE LIST IS A STATE THE ROM REACHES, and it comes with a NULL rover: `Malloc` of the
    # last free block exactly unlinks it through the MPB and then stores `mp_mfl` — now 0 — as the
    # rover (`gemdos_md_alloc`'s own note). So a pool with no FREE span says `rover_span=None`, and
    # any other combination is a shape nothing produces.
    assert (rover_span is None) == (not free), (
        "a pool with no free span has a NULL rover and one with a free span has the rover on a "
        "descriptor — `rover_span=None` is how a case asks for the first")
    at = 0 if rover_span is None else free[rover_span].md

    pokes = dict(arena.pokes)
    for index, span in enumerate(free):
        link = free[index + 1].md if index + 1 < len(free) else 0
        pokes.update(_descriptor_poke(span.md, link, span.start, span.length, 0))
    # The desktop's own allocated list stays below whatever the case pushes in front of it.
    tail = case.long_in(BASE_IMAGE, GEMDOS_MPB + addrs.MPB_ALLOCATED_LIST)
    owner = case.long_in(BASE_IMAGE, addrs.GEMDOS_P_RUN)
    for index, span in enumerate(used):
        link = used[index + 1].md if index + 1 < len(used) else tail
        pokes.update(_descriptor_poke(span.md, link, span.start, span.length, owner))
    # A RECYCLED descriptor still holds the fields of the block it last described — `gemdos_pool_free`
    # overwrites only its first longword, with the chain link — so the spares are staged that way and
    # not as zeroes. That is what makes `gemdos_pool_get`'s CLEAR a visible store: over a virgin
    # arena record it writes zeroes onto zeroes and no byte moves.
    for index, md in enumerate(spare):
        link = spare[index + 1] if index + 1 < len(spare) else 0
        pokes[md] = struct.pack(">IIII", link, SNAPSHOT_FREE_MD.start,
                                STALE_DESCRIPTOR_LENGTH * (index + 1), owner)

    pokes[GEMDOS_MPB] = struct.pack(">III", free[0].md if free else 0,
                                    used[0].md if used else tail, at)
    pokes[GEMDOS_P_ROOT + MD_SIZE_CLASS * POOL_CHAIN_ENTRY_BYTES] = \
        struct.pack(">I", spare[0] if spare else 0)
    pokes.update(arena.counters())
    if arena_words_left is not None:
        pokes[GEMDOS_POOL_FREE_WORDS] = struct.pack(">H", arena_words_left)
    return Staged(pokes, laid, free, used, at, spare, arena.next_record())


def after_running(entry, pokes):
    """`pokes` for the machine ONE CALL LATER: the staged pool with the ORIGINAL's own stores on it.

    Some pool states are reachable only through a routine that produces them — a free descriptor
    whose length has bit 31 set exists because `gemdos_mshrink`'s growth check is signed, and
    nothing a stager may legitimately write puts one there (`stage` requires the descriptors to tile
    the TPA, which a wrapped length cannot). So the case that needs one RUNS the routine that makes
    it, under the oracle, and starts from what it left.

    It is the playbook's rule for a fixture — the fixture is the ORIGINAL's own work rather than a
    hand transcription of what it would have done — applied to one call instead of a boot. The
    result is pokes rather than an image so that it composes with `make_image` like any other
    staging, and the input pokes are expanded to single bytes first: a one-byte store inside a
    longword poke must land ON it, not replace it.

    THE ARGUMENT FRAME IS DROPPED, along with everything else in the band the image comparison
    excludes. It is the first call's frame, and carrying it forward would overwrite the arguments
    the next case stages at the same address with the ones this one used — silently, because both
    are legitimate pokes and the later dict wins.
    """
    spread = {address + step: bytes([byte])
              for address, data in pokes.items() for step, byte in enumerate(data)
              if in_diff(address + step)}
    _final, writes, _regs = emu.run(make_image(pokes), entry, dict(ENTRY_REGS))
    return {**spread, **{address: bytes([value]) for address, value in writes.items()
                         if in_diff(address)}}


# ---- what a case checks instead of the attribution pass -------------------------------------------

def stores(info):
    """The oracle's write ledger WITHOUT the stack band — the stores that are about the routine.

    Every run of one of these routines writes its own `link`/`movem` frame, and those bytes are in
    the ledger like any other. They are also the bytes the image comparison excludes, so a case
    asking "did this call store anything at all?" has to ask it of the compared region.
    """
    return {address: value for address, value in info["writes"].items() if in_diff(address)}


def _written_runs(info):
    """The oracle's write ledger as maximal CONTIGUOUS runs of addresses, in address order.

    A run is the unit the check below works in, because the ledger is bytes and a store is not: a
    word store whose high byte happened to already hold the right value is still a store a candidate
    cannot skip, and asking each BYTE to have moved would name half the fields in this group as
    idempotent. A run is a field, or a group of adjacent fields written together — which is the
    granularity at which "the candidate did not write here at all" is the failure being caught.
    """
    addresses = sorted(stores(info))
    runs, at = [], 0
    while at < len(addresses):
        end = at + 1
        while end < len(addresses) and addresses[end] == addresses[end - 1] + 1:
            end += 1
        runs.append((addresses[at], end - at))
        at = end
    return runs


def assert_every_store_moved_a_byte(info, pokes, settled=()):
    """Every RUN of bytes the ORACLE stored contains at least one byte that differs from what the
    staged image held there.

    THIS IS THIS GROUP'S ATTRIBUTION CHECK, and the module docstring says why it is not `poison`.
    What it buys is the property poison exists for: if a run contains a byte that moved, then a
    candidate that never wrote that run leaves the old value there and the ordinary image compare
    reddens. What it costs is that a case has to be STAGED so the property holds — which is itself
    the discipline that makes these cases sharp, since a request that happens to leave the rover
    where it already was is a request that proves nothing about the rover.

    WHAT IT DOES NOT CATCH, stated because it is the limit: a candidate that wrote PART of a run
    whose other part moved. The ledger records bytes rather than stores, so the runs are fields
    written together and not individual `move.l`s; each battery states the fields it cares about
    separately, out of `case.written_long`, and the mutation sweep is what measures the rest.

    `settled` is `(address, length, why)` spans covering the runs that are genuinely idempotent in
    this case. The check requires the named bytes to be EXACTLY the invisible runs, so a case that
    stops being sharp fails here rather than quietly losing its attribution.
    """
    before = make_image(pokes)
    invisible = set()
    for at, length in _written_runs(info):
        if all(before[address] == info["writes"][address] for address in range(at, at + length)):
            invisible.update(range(at, at + length))
    named = {address + step for address, length, _why in settled for step in range(length)}
    assert invisible == named, (
        f"the stores this case cannot attribute are {sorted(hex(a) for a in invisible)}, but it "
        f"names {sorted(hex(a) for a in named)} — every run of bytes the ROM wrote must hold at "
        f"least one byte that differs from what was there (so a candidate that skipped the store "
        f"reddens) or be named here with the reason it cannot")


# ---- entering one of these routines ---------------------------------------------------------------
# They are ordinary Alcyon C functions, entered with a `jsr` and reading their arguments off the
# frame at 8(A6) — which is `abi.FIRST_ARG`, the same slot the BIOS/XBIOS batteries stage words in.
# A5 IS NOT LOAD-BEARING HERE: GEMDOS's compiled C reaches its globals by absolute address
# (`move.l $87ce,a0`) rather than through the BIOS dispatcher's `suba.l a5,a5`, so it is passed as 0
# for the project's usual reason — a register a case does not declare is a register a case is not
# about — and nothing here reads it.
ENTRY_REGS = {"a5": 0}


def mshrink_args(block, new_length):
    """`Mshrink`'s own frame, which is a reserved ZERO WORD and then the two longwords.

    The word is what puts `block` at 10(A6) and `new_length` at 14(A6); the ROM never reads it, so
    the core takes two parameters where the frame has three slots. Every other routine here takes
    plain longwords and uses `case.long_args`.
    """
    return case.args(">HII", 0, block & 0xFFFFFFFF, new_length & 0xFFFFFFFF)


def run(entry, glue, pokes, *, width=case.FULL_D0, settled=()):
    """One differential on this group's shape: no poison, and the store check above instead."""
    info = case.run(entry, {**ENTRY_REGS, "_pokes": pokes}, glue, width=width, poison=False)
    assert_every_store_moved_a_byte(info, pokes, settled)
    return info


# ---- what the orchestrator needs from this group ---------------------------------------------------
# Every field these batteries READ or POKE, as whole spans, for `test_boot_snapshot.py`'s
# `CASE_FIELDS` — the check that no masked region (a byte two captures of the same boot disagree
# about) covers something a case rests on. Declared here rather than in each battery because the
# four share one pool: the spans are the pool's, not any one routine's.
#
# NOT REPEATED HERE, because `CASE_FIELDS` already declares them for other batteries: `_membot`/
# `_memtop` (the TPA the tiling case reads), `OS_MEMORY_DESCRIPTOR` (which is on this machine's
# allocated list, so `Mfree` of the list's tail reaches it), `abi.FIRST_ARG` (Mshrink's frame is
# ten bytes, inside the twelve declared there), and `p_run` — the basepage `gemdos_md_alloc` stamps
# into `m_own` — which `test/gemdos.py` declares for the whole wave.
CASE_SPANS = (
    (GEMDOS_MPB, 12, "GEMDOS's own memory parameter block — mfl, mal and the rover"),
    (GEMDOS_P_ROOT, (BASEPAGE_SIZE_CLASS + 1) * POOL_CHAIN_ENTRY_BYTES,
     "the pool's free chain per size class, up to the basepage class a case files a record under"),
    (GEMDOS_POOL_ARENA, GEMDOS_POOL_ARENA_WORDS * 2,
     "the record arena: every memory descriptor the machine has, and the ones a case cuts"),
    (GEMDOS_POOL_USED_WORDS, 2, "the arena's bump cursor"),
    (GEMDOS_POOL_FREE_WORDS, 2, "...and the words it has left"),
    # The 68000's first three vectors, which `Mshrink` writes through when the pool is spent — a
    # ROM defect this group reproduces rather than corrects
    # (`test_gemdos_memory_mshrink.py::test_a_spent_descriptor_pool_makes_mshrink_write_through_null`).
    (0, 12, "the reset vectors a spent-pool Mshrink stores a descriptor into"),
)
