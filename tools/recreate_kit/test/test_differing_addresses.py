"""`harness.differing_addresses` held to its definition — every address of the spans where the two images differ
and the exclusion says nothing, ascending — and to what it may LOOK AT on the way: a chunk that differs is narrowed
to its lines that differ before any byte is walked.
"""
import random

import kit_smoke_project

kit_smoke_project.bind()

from recreate_kit import harness   # noqa: E402  (importable only once a project is bound)

CHUNK, LINE = harness.DIFF_CHUNK_BYTES, harness.DIFF_LINE_BYTES
IMAGE_BYTES = 3 * CHUNK + 5 * LINE + 7                  # a last chunk, and a last line, that are short
SPANS = ((LINE + 3, CHUNK + 2 * LINE + 1), (2 * CHUNK - 9, IMAGE_BYTES))        # ...begun and ended off every boundary
SEEDS = range(6)


def _by_definition(left, right, spans, excluded):
    return [at for lo, hi in spans for at in range(lo, hi) if left[at] != right[at] and not excluded(at)]


def _two_images(seed):
    """Two images that differ in a few scattered bytes, a run across a line's end and one across a chunk's."""
    chosen = random.Random(seed)
    left = bytearray(chosen.randbytes(IMAGE_BYTES))
    right = bytearray(left)
    differing = {chosen.randrange(IMAGE_BYTES) for _each in range(40)}
    differing |= set(range(3 * LINE - 2, 3 * LINE + 2)) | set(range(2 * CHUNK - 3, 2 * CHUNK + 3))
    differing |= {0, IMAGE_BYTES - 1, SPANS[0][0], SPANS[0][1] - 1, SPANS[0][1], SPANS[1][0] - 1, SPANS[1][0]}
    for at in differing:
        right[at] ^= 0xFF
    return left, right, sorted(differing)


def test_the_addresses_found_are_the_definition_s_in_its_order():
    for seed in SEEDS:
        left, right, differing = _two_images(seed)
        dropped = set(differing[::3])
        found = harness.differing_addresses(memoryview(left), memoryview(right), SPANS, dropped.__contains__)
        assert found == _by_definition(left, right, SPANS, dropped.__contains__) and found, f"seed {seed}"
        assert found == sorted(found) and not dropped & set(found)
        whole = ((0, IMAGE_BYTES),)
        assert harness.differing_addresses(memoryview(left), memoryview(right), whole, lambda at: False) == differing


def test_the_exclusion_is_asked_about_the_addresses_that_differ_and_no_other():
    """...each once, ascending: an exclusion may be anything a caller wrote, and is never asked about an equal byte."""
    left, right, differing = _two_images(0)
    asked = []
    harness.differing_addresses(memoryview(left), memoryview(right), SPANS, lambda at: asked.append(at) or False)
    assert asked == [at for at in differing if any(lo <= at < hi for lo, hi in SPANS)]


class _CountingBytes:
    """An image that counts the single bytes read out of it (a slice is one compare's worth, read in C)."""

    def __init__(self, image):
        self.image, self.bytes_read = bytes(image), 0

    def __getitem__(self, at):
        if not isinstance(at, slice):
            self.bytes_read += 1
        return self.image[at]


def test_one_differing_byte_does_not_have_its_whole_chunk_walked():
    """THE RED for a walk as wide as the chunk: one byte that differs (a dropped word of a green case) cost 65,536
    byte reads of each image to find — and to exclude. Narrowed to the line it is in first: none read singly out
    of the images at all, the line's bytes compared out of the chunk already in hand."""
    plain = bytearray(IMAGE_BYTES)
    other = bytearray(plain)
    other[CHUNK + 5] = 1
    left, right = _CountingBytes(plain), _CountingBytes(other)
    assert harness.differing_addresses(left, right, ((0, IMAGE_BYTES),), lambda at: False) == [CHUNK + 5]
    assert left.bytes_read + right.bytes_read == 0
