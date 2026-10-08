"""`harness.differing_addresses` held to its definition — every address of the spans where the two images differ
and the exclusion says nothing, ascending — and to what it may LOOK AT on the way: a chunk that is EQUAL is found so
where it lies, neither side copied; a chunk that differs is narrowed to its lines that differ before any byte is
walked.
"""
import ctypes
import random
import tracemalloc

import pytest

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


# ---- an equal chunk is found IN PLACE ------------------------------------------------------------------------------------
# What a caller may hand in, by how the compare can reach its bytes: the three it finds an address for, and the two
# it cannot (a read-only view that is not the whole of a `bytes`; an object that is no memoryview) and copies.
def _as_a_bytearray(image):
    return memoryview(bytearray(image))


def _as_bytes(image):
    return memoryview(bytes(image))


def _as_a_ctypes_array(image):
    return memoryview((ctypes.c_uint8 * len(image)).from_buffer(bytearray(image))).cast("B")


def _as_a_slice_of_bytes(image):
    return memoryview(b"\xa5" + bytes(image))[1:]


IN_PLACE = {"a bytearray": _as_a_bytearray, "bytes, whole": _as_bytes, "a ctypes array": _as_a_ctypes_array}
COPIED = {"a slice of bytes": _as_a_slice_of_bytes, "no memoryview": _CountingBytes}
EVERY_KIND = {**IN_PLACE, **COPIED}
# One byte, alone in the image, wherever a chunk's arithmetic could lose it: a chunk's first and last, the short last
# chunk's last, and the bytes either side of a span's two ends.
LONE_BYTES = (0, CHUNK - 1, CHUNK, 2 * CHUNK - 1, 3 * CHUNK, IMAGE_BYTES - 1, SPANS[0][0], SPANS[0][1] - 1, SPANS[1][0])


@pytest.mark.parametrize("kind", EVERY_KIND)
def test_one_byte_that_differs_is_found_wherever_it_lies_whatever_holds_the_images(kind):
    """THE SAME ANSWER IN PLACE AND COPIED: a lone byte at every edge a chunk has, each image of each kind."""
    plain = bytes(random.Random(7).randbytes(IMAGE_BYTES))
    for at in LONE_BYTES:
        other = bytearray(plain)
        other[at] ^= 0x80
        for spans in (SPANS, ((0, IMAGE_BYTES),)):
            expected = _by_definition(plain, other, spans, lambda _at: False)
            assert harness.differing_addresses(EVERY_KIND[kind](plain), EVERY_KIND[kind](other), spans,
                                               lambda _at: False) == expected, f"{at:#x} over {spans}"


@pytest.mark.parametrize("kind", IN_PLACE)
def test_an_image_s_address_is_where_its_bytes_lie(kind):
    """...and `_address_of` answers the buffer's own first byte: the byte read there through ctypes is the image's."""
    image = bytes(random.Random(3).randbytes(4 * LINE))
    view = IN_PLACE[kind](image)
    assert ctypes.string_at(harness._address_of(view), len(image)) == image
    of_a_slice = harness._address_of(view[LINE:])
    if view.readonly:
        assert of_a_slice is None, "a slice of `bytes` starts somewhere its view does not say"
    else:
        assert ctypes.string_at(of_a_slice, 2 * LINE) == image[LINE:3 * LINE]


@pytest.mark.parametrize("kind", COPIED)
def test_an_image_with_no_address_this_can_name_is_copied_as_it_ever_was(kind):
    assert harness._address_of(COPIED[kind](bytes(LINE))) is None


def test_equal_images_are_compared_without_copying_a_chunk_of_either():
    """THE RED for the copies: two equal images, three chunks and a short one — every chunk of both used to be
    copied out before anything was compared (two chunks alive at once). In place: nothing the size of a chunk is
    allocated at all."""
    image = random.Random(11).randbytes(IMAGE_BYTES)
    left, right = _as_a_bytearray(image), _as_a_ctypes_array(image)
    tracemalloc.start()
    try:
        before, _peak = tracemalloc.get_traced_memory()
        tracemalloc.reset_peak()
        assert harness.differing_addresses(left, right, ((0, IMAGE_BYTES),), lambda _at: False) == []
        _now, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak - before < CHUNK, f"an equal compare allocated {peak - before} bytes: a chunk is {CHUNK}"


def test_no_chunk_is_compared_in_place_past_the_end_of_either_image(monkeypatch):
    """A SPAN THAT RUNS PAST A BUFFER: a slice stops at the end by itself; a `memcmp` would read on. So a chunk is
    compared in place only where BOTH images hold all of it — every call lies inside the shorter one — and the
    answer is the one the copies gave."""
    compared = []

    def memcmp(here, there, count):
        compared.append((here, there, count))
        return ctypes.CDLL(None).memcmp(ctypes.c_void_p(here), ctypes.c_void_p(there), ctypes.c_size_t(count))
    monkeypatch.setattr(harness, "_memcmp", memcmp)
    image = random.Random(5).randbytes(IMAGE_BYTES)
    left, right = _as_a_bytearray(image), _as_a_bytearray(image[:2 * CHUNK + LINE])
    here, there = harness._address_of(left), harness._address_of(right)
    assert harness.differing_addresses(left, right, ((0, 2 * CHUNK),), lambda _at: False) == []
    assert compared == [(here, there, CHUNK), (here + CHUNK, there + CHUNK, CHUNK)]
    compared.clear()
    with pytest.raises(IndexError):                     # the walk's own answer to an image that ends inside a span
        harness.differing_addresses(left, right, ((2 * CHUNK, IMAGE_BYTES),), lambda _at: False)
    assert compared == [], "the chunk the shorter image ends inside was never handed to memcmp"


def test_no_chunk_is_compared_in_place_before_the_start_of_an_image(monkeypatch):
    """THE RED for the lower bound (a span that began below 0 was handed to `memcmp` at `here + start` — bytes BEFORE
    both buffers: a dead worker, or two unrelated regions of the heap compared equal and the chunk skipped): such a
    chunk is never compared in place; the slices answer for it, as they did — counting a negative index from the
    image's end."""
    compared = []

    def memcmp(here, there, count):
        compared.append((here, there, count))
        return 0                        # ...and reads nothing: a chunk handed over here lies outside both buffers
    monkeypatch.setattr(harness, "_memcmp", memcmp)
    image = random.Random(7).randbytes(IMAGE_BYTES)
    left, right = _as_a_bytearray(image), _as_a_bytearray(image)
    below = (LINE - IMAGE_BYTES, 2 * LINE - IMAGE_BYTES)          # the image's second line, named from its end
    assert harness.differing_addresses(left, right, (below,), lambda _at: False) == []
    assert compared == [], "a chunk below the image's start was handed to memcmp"
    right[LINE] ^= 0xFF
    assert harness.differing_addresses(left, right, (below,), lambda _at: False) == [below[0]]
    assert compared == []


@pytest.mark.parametrize("spans", [(), ((0, 0),), ((0, LINE),)], ids=["no span", "an empty span", "a span past it"])
def test_an_image_of_no_bytes_is_compared_as_the_copies_compared_it(spans):
    """THE RED for the empty image (a WRITABLE view of no bytes made ctypes raise "Buffer size too small" before a
    span was looked at, even with none): it has no address, so its slices answer — nothing differs in no bytes."""
    empty = memoryview(bytearray())
    assert harness._address_of(empty) is None and harness._address_of(memoryview(b"")) is None
    assert harness.differing_addresses(empty, memoryview(bytearray()), spans, lambda _at: False) == []
    assert harness.differing_addresses(memoryview(b""), empty, spans, lambda _at: False) == []
