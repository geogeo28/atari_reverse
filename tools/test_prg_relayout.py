"""Pin ``tools/prg_relayout.py``: the run-time relayout must move exactly what crt0 moves.

Built on a synthetic minimal .PRG rather than a game, so every expectation is arithmetic. The
image is laid out so that all three interesting cases appear at once: a fixup **in TEXT pointing
into DATA** (its value must be rewritten), a fixup **located in DATA** (its position must move up
by the BSS length), and a fixup pointing into TEXT (nothing may change). The regression this
guards is a relayout that shifts one of the two halves of a fixup — position or target — and not
the other, which produces an image that disassembles beautifully and is wrong.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prg_dis                                        # noqa: E402
import prg_relayout                                   # noqa: E402

TLEN = 0x20
DLEN = 0x10
BLEN = 0x40
TEXT_FIXUP = 0x04                 # in TEXT, points into DATA
TEXT_FIXUP_TARGET = TLEN + 0x8    # ... at DATA+8
DATA_FIXUP = TLEN + 0x0           # in DATA, points into TEXT
DATA_FIXUP_TARGET = 0x1c
TEXT_ONLY_FIXUP = 0x10            # in TEXT, points into TEXT: must not move at all
TEXT_ONLY_TARGET = 0x18


def _build_prg():
    """A file-layout .PRG whose TEXT/DATA bytes are distinguishable filler plus three fixups."""
    image = bytearray(b"\xaa" * TLEN + b"\xdd" * DLEN)
    for pos, target in ((TEXT_FIXUP, TEXT_FIXUP_TARGET),
                        (DATA_FIXUP, DATA_FIXUP_TARGET),
                        (TEXT_ONLY_FIXUP, TEXT_ONLY_TARGET)):
        struct.pack_into(">I", image, pos, target)
    header = struct.pack(prg_relayout.HEADER_FMT, prg_relayout.PRG_MAGIC,
                         TLEN, DLEN, BLEN, 0, 0, 0, 0)
    fixups = sorted((TEXT_FIXUP, TEXT_ONLY_FIXUP, DATA_FIXUP))
    return bytes(header + image + prg_relayout.encode_reloc_table(fixups)), bytes(image)


def _relayed():
    src, image = _build_prg()
    out = prg_relayout.relayout(src, log=lambda *a: None)
    head = prg_dis.parse_header(out)
    body = out[prg_dis.HEADER_LEN:prg_dis.HEADER_LEN + head["tlen"] + head["dlen"]]
    return out, head, body, image


def test_header_folds_bss_into_text():
    _out, head, _body, _image = _relayed()
    assert (head["tlen"], head["dlen"], head["blen"]) == (TLEN + BLEN, DLEN, 0)


def test_text_bytes_are_untouched_and_the_bss_gap_is_zero():
    _out, _head, body, image = _relayed()
    assert body[:TEXT_FIXUP] == image[:TEXT_FIXUP]
    assert body[TEXT_FIXUP + 4:TLEN] == image[TEXT_FIXUP + 4:TLEN]
    assert body[TLEN:TLEN + BLEN] == b"\0" * BLEN


def test_data_bytes_are_the_same_bytes_at_the_runtime_offset():
    _out, _head, body, image = _relayed()
    moved = body[TLEN + BLEN:TLEN + BLEN + DLEN]
    assert moved[4:] == image[TLEN + 4:TLEN + DLEN]        # everything past the DATA fixup


def test_fixup_positions_move_with_their_segment():
    out, head, _body, _image = _relayed()
    assert sorted(prg_dis.parse_reloc(out, head)) == sorted(
        (TEXT_FIXUP, TEXT_ONLY_FIXUP, DATA_FIXUP + BLEN))


def test_fixup_target_into_data_is_retargeted():
    _out, _head, body, _image = _relayed()
    assert struct.unpack_from(">I", body, TEXT_FIXUP)[0] == TEXT_FIXUP_TARGET + BLEN


def test_fixup_target_into_text_is_left_alone():
    _out, _head, body, _image = _relayed()
    assert struct.unpack_from(">I", body, TEXT_ONLY_FIXUP)[0] == TEXT_ONLY_TARGET
    assert struct.unpack_from(">I", body, DATA_FIXUP + BLEN)[0] == DATA_FIXUP_TARGET


def test_runtime_offset_maps_the_three_segments():
    assert prg_relayout.runtime_offset(TLEN - 1, TLEN, DLEN, BLEN) == TLEN - 1
    assert prg_relayout.runtime_offset(TLEN, TLEN, DLEN, BLEN) == TLEN + BLEN
    assert prg_relayout.runtime_offset(TLEN + DLEN, TLEN, DLEN, BLEN) == TLEN
    assert prg_relayout.runtime_offset(TLEN + DLEN + BLEN - 1, TLEN, DLEN, BLEN) == TLEN + BLEN - 1


def test_reloc_table_round_trips_through_a_span():
    """A gap wider than a byte needs RELOC_SKIP runs; the encoder is parse_reloc's inverse."""
    fixups = [0x10, 0x14, 0x14 + 3 * prg_dis.RELOC_SKIP_BYTES + 6]
    table = prg_relayout.encode_reloc_table(fixups)
    assert sorted(prg_dis.parse_reloc(table, {"reloc_off": 0, "absf": 0})) == fixups
