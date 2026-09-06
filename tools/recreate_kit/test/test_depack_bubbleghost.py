#!/usr/bin/env python3
"""Regression checks for depack_bubbleghost's container handling and its decrypt.

Three layers, cheapest first:

  1. The header and entry-stub guards, on SYNTHETIC bytes — a shipped GHOST.PRG can never
     exercise them, and a wrapper build this tool does not understand must be refused rather
     than silently mis-decrypted.
  2. The buried relocation stream, on a hand-built bytearray. The span the depacker re-emits is
     its own; the FIXUPS come from ``prg_dis.parse_reloc``, so what is checked here is the two
     ends the game's own stream never shows: a `01` skip byte (the byte whose mis-parse once
     corrupted every project's Ghidra DB) and a stream with no terminator.
  3. End-to-end on the real dump, pinned by hash both sides. Nothing copyrighted lives in this
     file — it holds the digests only, and skips when the dump is absent.

Runs under the kit's suite (``make -C tools/recreate_kit test``).
"""
import hashlib
import struct
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[2]          # reverse/tools
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(TOOLS))
import depack_bubbleghost                            # noqa: E402
import prg_dis                                       # noqa: E402

GHOST_PRG = REPO / "projects" / "bubbleghost" / "bin" / "GHOST.PRG"
# The dump this tool was written against, and what it must decrypt to. Digests, not bytes: the
# game is copyrighted, and a pin on the OUTPUT is what catches a decrypt that drifts.
GHOST_PRG_SHA256 = "46266ef918179eb37662cb47f794214577429935638895cd66c26d4250c4e633"
GHOST_PLAIN_SHA256 = "c8acef97b6c6d1f4e892566f3239c436c6fcae10c7f3e5c93628a6e6249d701f"

# A synthetic image big enough to hold the entry stub, with a `jmp` displacement of 0 — which
# lands the wrapper entry exactly ON the bss base, one byte past the data segment it must be in.
STUB_TEXT_LEN = 0x10
STUB_DATA_LEN = 0x10
BAD_DISPLACEMENT = b"\x00\x00"

# Layer 2's fixture: 0x40 bytes of "image" (all zero, so every relocated pointer is in range),
# then the stream. 0x10, an 8-byte step to 0x18, one 254-byte span, terminator.
IMAGE_END = 0x40
RELOC_SPAN = bytes([0, 0, 0, 0x10, 8, prg_dis.RELOC_SKIP, prg_dis.RELOC_END])
RELOC_FIXUPS = [0x10, 0x18]


def _prg(text_len, data_len, image):
    """A .PRG header describing `image`, for the guards that run before any decrypt."""
    header = struct.pack(prg_dis.PRG_HEADER_FORMAT, depack_bubbleghost.PRG_MAGIC_WORD,
                         text_len, data_len, 0, 0, 0, 0, 0)
    return header + image


def _stub(displacement):
    return (depack_bubbleghost.STUB_HEAD + b"\x00\x00" + depack_bubbleghost.STUB_JUMP
            + displacement)


def _refused(data, message):
    with pytest.raises(depack_bubbleghost.DepackError, match=message):
        depack_bubbleghost.decode(data)


def test_non_prg_input_is_refused():
    _refused(b"", "not a GEMDOS .PRG")
    _refused(_prg(0, 0, b"")[2:], "not a GEMDOS .PRG")     # shorter than a whole header


def test_header_longer_than_the_file_is_refused():
    """A text length past the last byte must raise, not slice a short image and decrypt it."""
    _refused(_prg(0x1000, 0, b"\x00" * 16), "more image than the file holds")


def test_foreign_entry_stub_is_refused():
    """Everything is located from the stub, so a different build must be rejected outright."""
    _refused(_prg(0x20, 0, b"\x00" * 0x20), "not the Bubble Ghost wrapper stub")


def test_stub_displacement_outside_the_data_segment_is_refused():
    image = _stub(BAD_DISPLACEMENT).ljust(STUB_TEXT_LEN + STUB_DATA_LEN, b"\x00")
    _refused(_prg(STUB_TEXT_LEN, STUB_DATA_LEN, image), "outside the data segment")


def test_reloc_span_stops_at_the_terminator_and_skips_record_no_fixup():
    """The `01` byte spans 254 bytes and fixes up NOTHING — see docs/binary-formats.md."""
    image = bytearray(IMAGE_END) + RELOC_SPAN + b"\xde\xad"      # trailing bytes are not the table
    span, fixups = depack_bubbleghost._reloc_stream(image, IMAGE_END)
    assert span == RELOC_SPAN, "the re-emitted table is not the stream's own bytes"
    assert fixups == RELOC_FIXUPS, (
        "a skip byte was recorded as a fixup (or the span's own bytes were mis-walked)")


def test_unterminated_reloc_stream_is_refused():
    image = bytearray(IMAGE_END) + RELOC_SPAN[:-1]
    with pytest.raises(depack_bubbleghost.DepackError, match="not terminated"):
        depack_bubbleghost._reloc_stream(image, IMAGE_END)


def test_fixup_outside_the_image_is_refused():
    """A fixup past the image's end means the decrypt produced the wrong bytes, not a table."""
    beyond = bytes([0, 0, 0, IMAGE_END, prg_dis.RELOC_END])
    image = bytearray(IMAGE_END) + beyond
    with pytest.raises(depack_bubbleghost.DepackError, match="not a longword inside the image"):
        depack_bubbleghost._reloc_stream(image, IMAGE_END)


@pytest.mark.skipif(not GHOST_PRG.exists(), reason="projects/bubbleghost/bin/GHOST.PRG is absent")
def test_the_shipped_prg_decrypts_to_the_pinned_image():
    packed = GHOST_PRG.read_bytes()
    if hashlib.sha256(packed).hexdigest() != GHOST_PRG_SHA256:
        pytest.skip("%s is a different dump than this tool was pinned against" % GHOST_PRG.name)
    assert hashlib.sha256(depack_bubbleghost.decode(packed)).hexdigest() == GHOST_PLAIN_SHA256
