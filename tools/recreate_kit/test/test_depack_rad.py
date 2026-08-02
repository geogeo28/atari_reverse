#!/usr/bin/env python3
"""Regression checks for depack_rad's container handling.

Stdlib only, like ``tools/depack_rad.py`` itself. Runs under the kit's suite
(``cd tools/recreate_kit && make test``) or standalone:

    python3 tools/recreate_kit/test/test_depack_rad.py

The decode itself is pinned elsewhere and far harder: ``projects/wonderboy/notes/
rad_differential.py`` diffs all 41 .RAD streams on the two game disks against the ORIGINAL
68000 routine under Musashi. What is checked here is everything around that decode — the
header bounds, the longword alignment rule, the checksum gate, and each of the guards the
Python has and the 68000 does not — which the disks' own well-formed files can never exercise.
Four of those (the checksum, and depack_rad's three deviations) are pinned NOWHERE ELSE: the
damaged files on disk 2 refuse at an earlier guard, so they never reach them.

Every refusal is asserted against the NAMED guard that fired, not merely against DepackError.
The guards overlap — a malformed header trips several of them — so a type-only assertion lets
the guard a test was written for be deleted while a later one still refuses, and the test still
passes. That is exactly how three of these branches went unpinned before.

FIXTURE is SYNTHETIC, not game data: a 56-byte stream written by hand to exercise all six of
the format's tokens (both literal runs, all four match forms, including a match whose offset is
smaller than its length so the copy repeats itself). EXPECTED is not this depacker's own output
— it is what the game's 68000 routine produces from FIXTURE, taken from a run of
rad_differential.run_original(). So the fixture pins the decode against the original code, and
distributing it distributes nothing off the disk.
"""
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2]          # reverse/tools
sys.path.insert(0, str(TOOLS))
import depack_lsd                                    # noqa: E402 — only to pin the shared magic
import depack_rad                                    # noqa: E402

FIXTURE = bytes.fromhex(
    "0000002c000000409592908a00000407835a9a1aeac733353136323434e0e763"
    "6561666264606087c009064058011084b898a888d848505c")
EXPECTED = (b"ZYXWgfedcba98765ZYXWgfedcba9876543210"
            b"BBBBBBBBBBBBBBBBBB"
            b"AHGFEDCBA")

PACKED_LEN_OFF = 0           # header field that locates the end of the stream
UNPACKED_SIZE_OFF = 4        # header field the size cap guards
CHECKSUM_OFF = 8             # header field the stream's XOR has to cancel
SLACK = b"\x00" * 6          # what a cluster-rounded read, or a slice of a larger file, appends
PACKED_LEN = len(FIXTURE) - depack_rad.HDR_LEN
ODD_PACKED_LEN = PACKED_LEN - 2                           # not a multiple of 4
ABSURD_UNPACKED = 0xFFFFFFFF                              # a 4 GB bytearray, if it were believed
# One longword spliced in at the start of the stream and paid for in the packed length. The
# backwards walk stops before ever reaching it, so it is never read and never XORed in.
UNREAD_LONGWORD = bytes.fromhex("deadbeef")
# One byte less output than the stream decodes, so the last token runs off the front of it.
SHORT_UNPACKED = len(EXPECTED) - 1


def _with_field(data, off, value):
    """`data` with the big-endian long at `off` replaced — how a header is corrupted here."""
    return data[:off] + value.to_bytes(4, "big") + data[off + 4:]


def _depack(data):
    return depack_rad.depack(data, depack_rad.parse_header(data))


def _refuses(call, guard, what):
    """Assert `call()` is refused BY THE NAMED GUARD, rather than decoded, crashed, or refused
    by some other guard that happens to catch the same file."""
    try:
        call()
    except depack_rad.DepackError as exc:
        assert exc.guard == guard, ("%s was refused by the %r guard, not by %r (%s)"
                                    % (what, exc.guard, guard, exc))
        return
    except Exception as exc:                         # noqa: BLE001 — a raw exception is a defect too
        raise AssertionError("%s raised %s, not DepackError: %s" % (what, type(exc).__name__, exc))
    raise AssertionError("%s was accepted" % what)


def _refused(data, guard, what):
    """The whole decode must refuse `data` at `guard`."""
    _refuses(lambda: _depack(data), guard, what)


def test_fixture_decodes():
    got = _depack(FIXTURE)
    assert got == EXPECTED, "decoded %d bytes, first difference at %d" % (
        len(got), next((i for i, (a, b) in enumerate(zip(got, EXPECTED)) if a != b), len(EXPECTED)))


def test_trailing_slack_is_ignored():
    """EOF comes from the header, not from len(data) — so bytes past it must not change anything.

    Without that, a stream read in whole sectors, or sliced out of a larger file with the tail
    left on, is rejected outright or seeds the bit buffer from padding.
    """
    assert _depack(FIXTURE + SLACK) == EXPECTED


def test_packed_length_past_the_data_is_refused():
    """The case the header's packed length must still be loud about: it points outside the buffer."""
    _refused(_with_field(FIXTURE, PACKED_LEN_OFF, len(FIXTURE)),
             depack_rad.GUARD_STREAM_PAST_EOF, "a packed length reaching past the last byte")


def test_packed_length_off_the_longword_grid_is_refused():
    """The routine walks the stream by longwords, so a length off the grid never reaches +12.

    On the 68000 that is an address error, not a wrong answer; here it must be a clean refusal.
    Zero is the same guard's other half: it puts the end of the stream ON the header, so the seed
    read would take the checksum field for stream data.
    """
    _refused(_with_field(FIXTURE, PACKED_LEN_OFF, ODD_PACKED_LEN),
             depack_rad.GUARD_PACKED_LENGTH, "an unaligned packed length")
    _refused(_with_field(FIXTURE, PACKED_LEN_OFF, 0),
             depack_rad.GUARD_PACKED_LENGTH, "a packed length of zero")


def test_absurd_unpacked_size_is_refused_by_the_header():
    """A corrupt size must be refused by parse_header, BEFORE anything allocates it.

    Asserted against parse_header alone on purpose: routing it through depack() would allocate
    the very 4 GB bytearray this guard exists to prevent, and then be satisfied by whatever the
    decode failed with afterwards — which is why deleting the guard used to go unnoticed.
    """
    _refuses(lambda: depack_rad.parse_header(_with_field(FIXTURE, UNPACKED_SIZE_OFF,
                                                         ABSURD_UNPACKED)),
             depack_rad.GUARD_UNPACKED_TOO_BIG, "a 4 GB unpacked size")


def test_zero_unpacked_size_is_refused():
    """No output means the routine's bottom-of-loop test never runs, so it decodes one token
    below the destination. Refuse rather than model writing outside the buffer."""
    _refused(_with_field(FIXTURE, UNPACKED_SIZE_OFF, 0),
             depack_rad.GUARD_NO_OUTPUT, "a header claiming no output at all")


def test_bad_checksum_is_refused():
    """The gate the disks' own files can never reach — not even the four damaged ones, which
    refuse at an earlier guard (see rad_differential's KNOWINGLY UNPINNED note). This is the
    ONLY thing pinning it.

    Corrupting the header's checksum rather than a stream byte is deliberate: it reaches the
    checksum test with the decode itself still well-formed, so this pins the gate and not some
    earlier bounds check that a mangled stream would trip first.
    """
    stored = int.from_bytes(FIXTURE[CHECKSUM_OFF:CHECKSUM_OFF + 4], "big")
    _refused(_with_field(FIXTURE, CHECKSUM_OFF, stored ^ 1),
             depack_rad.GUARD_CHECKSUM, "a stream whose checksum does not cancel")


def test_stream_not_returning_to_the_header_is_refused():
    """DEVIATION, pinned: a clean checksum does NOT imply the stream was fully consumed.

    Splicing an extra longword in at the start of the stream and paying for it in the packed
    length leaves the decode identical — the backwards walk stops above it, so it is never read
    and never XORed in. The 68000 accepts that file and decodes it to EXPECTED (confirmed under
    Musashi); depack_rad refuses it, and this is the only test that says so.
    """
    padded = FIXTURE[:depack_rad.HDR_LEN] + UNREAD_LONGWORD + FIXTURE[depack_rad.HDR_LEN:]
    _refused(_with_field(padded, PACKED_LEN_OFF, PACKED_LEN + len(UNREAD_LONGWORD)),
             depack_rad.GUARD_STREAM_NOT_CLOSED, "a stream with one longword left unread")


def test_token_overrunning_the_output_start_is_refused():
    """DEVIATION, pinned: a token that runs past the START of the destination.

    Shrinking the claimed unpacked size by one byte makes the final match one byte too long. The
    68000 writes it below the buffer and exits (confirmed under Musashi); depack_rad refuses.
    No file on either disk reaches this guard, so this test is all that holds it.
    """
    _refused(_with_field(FIXTURE, UNPACKED_SIZE_OFF, SHORT_UNPACKED),
             depack_rad.GUARD_OUTPUT_OVERRUN, "a token overrunning the start of the output")


def test_the_two_depackers_agree_on_the_lsd_magic():
    """The two tools each own one container and do not import each other, so the one constant
    they must agree on is pinned here instead (CLAUDE.md, "one source of truth")."""
    assert depack_rad.LSD_MAGIC == depack_lsd.MAGIC, (
        "depack_rad would stop recognising LSD! streams: %r vs %r"
        % (depack_rad.LSD_MAGIC, depack_lsd.MAGIC))


def test_short_stored_and_lsd_files_are_refused():
    _refused(FIXTURE[:depack_rad.MIN_FILE_LEN - 1], depack_rad.GUARD_SHORT_FILE,
             "a file shorter than a header plus one longword")
    # SPRITES.CRU's shape: the container's stored form, which has no stream to decode at all.
    _refused(_with_field(FIXTURE, UNPACKED_SIZE_OFF, PACKED_LEN),
             depack_rad.GUARD_STORED_FORM, "the stored .CRU form")
    # The cracked release's cruncher: same 12-byte-header shape, entirely different stream.
    _refused(depack_rad.LSD_MAGIC + FIXTURE[4:], depack_rad.GUARD_LSD_MAGIC, "an LSD! stream")


if __name__ == "__main__":
    # Collected, not listed by hand: a list would let a new test be added and silently never run.
    tests = [fn for name, fn in sorted(globals().items()) if name.startswith("test_")]
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
