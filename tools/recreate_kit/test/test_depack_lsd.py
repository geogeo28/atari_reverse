#!/usr/bin/env python3
"""Regression checks for depack_lsd's container handling.

Stdlib only, like ``tools/depack_lsd.py`` itself. Runs under the kit's suite
(``cd tools/recreate_kit && make test``) or standalone:

    python3 tools/recreate_kit/test/test_depack_lsd.py

The decode itself is pinned elsewhere and far harder: ``projects/wonderboy/notes/
lsd_differential.py`` diffs all 96 streams on the game disk against the ORIGINAL 68000
routine under Musashi. What is checked here is everything around that decode — the header
bounds and the end-of-stream rule — which the disk's own well-formed files can never exercise.

FIXTURE is `1E50` from Wonder Boy in Monsterland's disk (projects/wonderboy/bin/extracted/),
the smallest LSD! stream on it, verbatim; EXPECTED is what the 68000 routine produces from it.
"""
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2]          # reverse/tools
sys.path.insert(0, str(TOOLS))
import depack_lsd                                    # noqa: E402

FIXTURE = bytes.fromhex(
    "4c5344210000003800000030a0050005b601000007ff8fff8ed5394030302a98"
    "0060841ef80070dac35000206e00000080d00000")
EXPECTED = bytes.fromhex(
    "0000000500058fff07ff07ff07ff8fff50002000000000"
    "00f8006000300020007000980060000000f80070000000000050002000000000"
    "00")

UNPACKED_SIZE_OFF = 4        # header field the size cap guards
EOF_FIELD_OFF = 8            # header field that locates the end of the stream
SLACK = b"\x00" * 6          # what a cluster-rounded read, or a slice of a larger file, appends


def _with_field(data, off, value):
    """`data` with the big-endian long at `off` replaced — how a header is corrupted here."""
    return data[:off] + value.to_bytes(4, "big") + data[off + 4:]


def _depack(data):
    return depack_lsd.depack(data, depack_lsd.parse_header(data))


def _refused(data, what):
    """Assert `data` is rejected as a DepackError rather than decoded or crashed."""
    try:
        _depack(data)
    except depack_lsd.DepackError:
        return
    except Exception as exc:                         # noqa: BLE001 — a raw exception is a defect too
        raise AssertionError("%s raised %s, not DepackError: %s" % (what, type(exc).__name__, exc))
    raise AssertionError("%s was accepted and decoded" % what)


def test_fixture_decodes():
    got = _depack(FIXTURE)
    assert got == EXPECTED, "decoded %d bytes, first difference at %d" % (
        len(got), next((i for i, (a, b) in enumerate(zip(got, EXPECTED)) if a != b), len(EXPECTED)))


def test_trailing_slack_is_ignored():
    """EOF comes from the header, not from len(data) — so bytes past it must not change anything.

    Without that, a stream read in whole sectors, or sliced out of a larger file with the tail
    left on, is rejected outright (the old filesize check) or seeds the bit buffer from padding.
    """
    assert _depack(FIXTURE + SLACK) == EXPECTED


def test_eof_field_past_the_data_is_refused():
    """The one case the header's EOF field must still be loud about: it points outside the buffer."""
    _refused(_with_field(FIXTURE, EOF_FIELD_OFF, len(FIXTURE)), "an EOF field past the last byte")


def test_absurd_unpacked_size_is_refused_before_allocating():
    """A corrupt size must raise, not ask Python for a 4 GB bytearray."""
    _refused(_with_field(FIXTURE, UNPACKED_SIZE_OFF, 0xFFFFFFFF), "a 4 GB unpacked size")


def test_short_and_magicless_files_are_refused():
    _refused(FIXTURE[:depack_lsd.MIN_FILE_LEN - 1], "a file shorter than a header plus its seed word")
    # The magic-less .RAD/.CRU container: a different cruncher with the same 12-byte header shape.
    _refused(b"\x00\x00\x00\x28" + FIXTURE[4:], "the magic-less container")


if __name__ == "__main__":
    tests = [test_fixture_decodes, test_trailing_slack_is_ignored,
             test_eof_field_past_the_data_is_refused,
             test_absurd_unpacked_size_is_refused_before_allocating,
             test_short_and_magicless_files_are_refused]
    failed = 0
    for t in tests:
        try:
            t()
            print("PASS %s" % t.__name__)
        except AssertionError as exc:
            failed += 1
            print("FAIL %s\n  %s" % (t.__name__, exc))
    print("%d/%d passed" % (len(tests) - failed, len(tests)))
    sys.exit(1 if failed else 0)
