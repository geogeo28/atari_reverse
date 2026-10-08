"""THE CANDIDATE'S IMAGE IS READ WHERE IT LIES (`harness.image_in_place`): the compare of a differential — and of its
attribution pass — is handed a view of the very buffer the candidate ran over, not a copy of it.

A copy was 16 MB a case in a ROM project and twice that under `poison`, made only to be compared and dropped. What
makes the view sound is ORDER, and that is what this holds: each compare is made before the next candidate run is
handed a buffer (`harness.candidate_image`, "Never live twice at once").

The module skips whole when the shared oracle or a C compiler is absent (`kit_smoke_project.bind`).
"""
import ctypes

from kit_smoke_project import CCONOUT_CHAR, EVENT_MALLOC_ENTRY, HEAP_RESULT, MALLOC_PROBE_SIZE, bind

harness = bind()


def _compares_of_a_poisoned_differential(monkeypatch):
    """`[(where the candidate's buffer lay, where the image compared as the candidate's lay)]`, a pass each."""
    buffers, compared, real = [], [], harness.differing_addresses

    def glue(lib, buf):
        buffers.append(ctypes.addressof(buf))
        return lib.g_logs_a_byte_and_allocates(buf, HEAP_RESULT, MALLOC_PROBE_SIZE, CCONOUT_CHAR)

    def differing_addresses(left, right, spans, excluded):
        compared.append(harness._address_of(right))
        return real(left, right, spans, excluded)
    monkeypatch.setattr(harness, "differing_addresses", differing_addresses)
    diffs, _info = harness.differential(EVENT_MALLOC_ENTRY, {}, glue, poison=True)
    assert diffs == []
    return list(zip(buffers, compared))


def test_both_passes_compare_the_buffer_the_candidate_ran_over(monkeypatch):
    """THE RED for the copy: the plain pass and the attribution pass each compared a `bytes` copy of the candidate's
    buffer — an image at another address. Each compares the buffer itself."""
    passes = _compares_of_a_poisoned_differential(monkeypatch)
    assert len(passes) == 2, "the premise: a poisoned differential runs the candidate twice and compares twice"
    for ran_over, compared in passes:
        assert compared == ran_over, "the image compared is not the buffer the candidate ran over"


def test_the_view_is_of_bytes_and_shows_a_later_store():
    """`image_in_place` answers a view — one byte an item, whatever the buffer's own item type — of the buffer's
    storage: a store made after it is seen through it (which is why every read precedes the next run)."""
    buf = harness.candidate_image(harness.make_image())
    view = harness.image_in_place(buf)
    assert (view.format, view.itemsize, len(view)) == ("B", 1, harness.IMAGE_SIZE)
    buf[HEAP_RESULT] ^= 0xFF
    assert view[HEAP_RESULT] == buf[HEAP_RESULT]


def test_the_view_a_compare_was_handed_is_dead_once_the_differential_returns(monkeypatch):
    """THE RED for the order being described and not enforced: the view each pass compared was still readable after
    its differential had returned — and under `guarded_image` the storage behind it is the NEXT run's. Released, a
    reader that outlives the compare fails loudly, in both passes; a copy taken while it lived is the reader's own."""
    handed, kept, real = [], [], harness.differing_addresses

    def differing_addresses(left, right, spans, excluded):
        handed.append(right)
        kept.append(bytes(right[HEAP_RESULT:HEAP_RESULT + 1]))
        return real(left, right, spans, excluded)
    monkeypatch.setattr(harness, "differing_addresses", differing_addresses)

    def glue(lib, buf):
        return lib.g_logs_a_byte_and_allocates(buf, HEAP_RESULT, MALLOC_PROBE_SIZE, CCONOUT_CHAR)
    diffs, _info = harness.differential(EVENT_MALLOC_ENTRY, {}, glue, poison=True)
    assert diffs == [] and len(handed) == 2 and len(kept) == 2
    for view in handed:
        try:
            view[HEAP_RESULT]
        except ValueError as released:
            assert "released" in str(released)
        else:
            raise AssertionError("a view of the candidate's image outlived the compare it was made for")
