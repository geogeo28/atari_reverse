"""The shared test-side building blocks: the GEMDOS Malloc probe's encoding, and the span seeder.

Both were copied between suites before they lived in `recreate_kit/stubs.py`, and both fail
QUIETLY when a copy is wrong. A stub with the wrong selector is still a serviced trap, so the run
comes back green having asked a different question; a seeder that lets two pokes cover one byte
writes the second over the first, which reads as "both regions were seeded" when only one was.

Neither needs a bound project or a build, so this runs in a bare checkout.
"""
import pytest

from recreate_kit import stubs


# ==================================================== the GEMDOS Malloc probe

def test_the_probe_is_the_instruction_sequence_it_documents():
    """Pinned as BYTES, because that is what the oracle executes — a constant renamed in the module
    would keep the docstring's spelling while the CPU saw something else."""
    assert stubs.gemdos_malloc_stub(0x1000).hex() == (
        "2f3c00001000"   # move.l #$1000,-(sp)
        "3f3c0048"       # move.w #$48,-(sp)      GEMDOS Malloc
        "4e41"           # trap #1
        "4fef0006"       # lea 6(sp),sp
        "4e75")          # rts


def test_the_probe_can_store_the_block_address_into_the_image():
    """A trap's return value is off-image, so a differential can only see it once it is stored."""
    assert stubs.gemdos_malloc_stub(0, store_result=0x30000).hex().endswith(
        "23c0000300004e75")   # move.l d0,$00030000 / rts


@pytest.mark.parametrize("size", (-1, stubs.MALLOC_LARGEST_FREE))
def test_the_largest_free_block_query_has_one_encoding(size):
    """`Malloc(-1)` is the canonical GEMDOS "how big is the largest free block?" query, and the two
    spellings a caller reaches for must assemble to the same longword."""
    assert stubs.gemdos_malloc_stub(size) == stubs.gemdos_malloc_stub(0xFFFFFFFF)


# ==================================================== the span seeder

def test_overlapping_spans_become_one_poke():
    """`harness.make_image` applies a poke dict in insertion order and the later one silently wins,
    so two pokes covering one byte would leave the first region half-seeded."""
    pokes = stubs.seed_spans(1, ((0x100, 0x200), (0x180, 0x300)))
    assert list(pokes) == [0x100]
    assert len(pokes[0x100]) == 0x200


def test_the_guard_widens_each_span_before_they_are_merged():
    """Widened FIRST: two spans that do not overlap can still collide once their guards are added,
    and merging before widening would produce exactly the double-covered byte above."""
    pokes = stubs.seed_spans(1, ((0x100, 0x180), (0x190, 0x200)), guard=0x10)
    assert list(pokes) == [0xF0]
    assert len(pokes[0xF0]) == 0x120


def test_disjoint_spans_stay_separate():
    """The control: merging is not "collapse everything into one buffer" — the bytes between two
    distant spans must stay as the image had them, or a case seeds regions it never named."""
    pokes = stubs.seed_spans(1, ((0x100, 0x180), (0x400, 0x480)))
    assert sorted(pokes) == [0x100, 0x400]


def test_the_same_seed_gives_the_same_bytes():
    """A case that fails is re-run from its seed, so the noise has to be reproducible."""
    assert stubs.seed_spans(7, ((0x100, 0x140),)) == stubs.seed_spans(7, ((0x100, 0x140),))
    assert stubs.seed_spans(7, ((0x100, 0x140),)) != stubs.seed_spans(8, ((0x100, 0x140),))
