"""Hand-assembled 68000 stubs, and the span seeder, shared by the kit's suite and the projects'.

A differential case often needs a few instructions the GAME does not contain — a GEMDOS call the
reconstruction reaches only through frames it cannot yet run, an entry the oracle can be pointed at.
Each such stub used to be assembled where it was needed, so one four-instruction sequence was spelt
in four files: two in the kit (``test/kit_smoke_project.py``, which builds it into a miniature
.PRG, and ``test/test_heap_base.py``, which drives that .PRG) and one in each project that asks the
model for a block. Nothing made the copies agree, and a bare hex string is the worst place for a
selector to be wrong: the trap is served, the run is green, and it answered a different question.

``seed_spans`` is here for the same reason and not because it is a stub: it was copied verbatim
between projects, and the copy that mattered had lost the merge step (see its docstring).

Importable with nothing built — it is plain byte arithmetic — so a suite can use it before, or
without, binding a project.
"""
import random
import struct

# ---- GEMDOS Malloc, the "give me a block" probe -------------------------------------------------
# `move.l #size,-(sp) / move.w #$48,-(sp) / trap #1 / lea 6(sp),sp / rts`, optionally storing the
# returned block address into the image first, since a trap's return value is off-image and a
# differential compares memory.
GEMDOS_MALLOC = 0x48             # the GEMDOS function number pushed as the selector word
GEMDOS_TRAP = 0x4E41             # trap #1
MALLOC_LARGEST_FREE = 0xFFFFFFFF  # Malloc(-1): GEMDOS's "how big is the largest free block?" query,
                                  # which the model serves fully and rounds to a ZERO-size bump — so
                                  # it reports the arena's base without moving the bump pointer
_MALLOC_FRAME_BYTES = 6          # the longword size + the selector word this stub pushed
_LEA_SP = 0x4FEF                 # lea d(sp),sp — the caller-pops half of the C convention
_MOVE_L_D0_ABS = 0x23C0          # move.l d0,<abs.l>
_RTS = 0x4E75


def gemdos_malloc_stub(size, store_result=None):
    """68000 asking TOS for a `size`-byte block and unwinding its own argument push, then `rts`.

    ``store_result`` is an absolute address to `move.l d0,` into before returning — what a case
    needs when the fact under test is the block's ADDRESS, which is otherwise off-image and so
    invisible to a memory diff.

    ``size`` is taken modulo 2**32, so the canonical ``MALLOC_LARGEST_FREE`` may equally be written
    as ``-1``: the caller pushes a longword either way, and refusing the negative spelling would
    only send it back through the same mask by hand.
    """
    code = (struct.pack(">HI", 0x2F3C, size & 0xFFFFFFFF)          # move.l #size,-(sp)
            + struct.pack(">HH", 0x3F3C, GEMDOS_MALLOC)            # move.w #$48,-(sp)
            + struct.pack(">H", GEMDOS_TRAP)                       # trap #1
            + struct.pack(">HH", _LEA_SP, _MALLOC_FRAME_BYTES))    # lea 6(sp),sp
    if store_result is not None:
        code += struct.pack(">HI", _MOVE_L_D0_ABS, store_result)   # move.l d0,<store_result>
    return code + struct.pack(">H", _RTS)


# ---- seeding ------------------------------------------------------------------------------------

def seed_spans(seed, spans, guard=0):
    """Noise over every byte a run touches, as a poke dict — the batteries' one seeder.

    `spans` is an iterable of (lo, hi); `guard` widens each by that many bytes either side. Spans
    are widened FIRST and merged after, so two pokes never cover one byte: `harness.make_image`
    applies a poke dict in insertion order and the later one silently wins, which reads as "both
    regions were seeded" when only one was.

    The merge is the whole reason this is shared rather than re-typed: it was written three times in
    one change in projects/zynaps and one of the three copies lacked it.
    """
    widened = sorted([lo - guard, hi + guard] for lo, hi in spans)
    merged = []
    for lo, hi in widened:
        if merged and lo <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    rng = random.Random(seed)
    return {lo: rng.randbytes(hi - lo) for lo, hi in merged}
