"""`case.merge_pokes` held to its definition: poke dicts laid over each other BYTE BY BYTE, later layers winning, as one
dict of maximal runs. The module builds the answer run-wise (the extents, then a slice store per piece); the reference
here is the definition spelt per byte, and the two are held equal over random layers — overlapping, adjacent, empty,
bytes and lists of ints alike.

...and `case.Result`'s image of the machine after a run: built when a case first reads it, once; the refusal of an
overflowed ledger made when the run ends, whether or not anyone reads the image."""
import random

import pytest

import case
from harness import make_image

ROUNDS_PER_SEED = 4000
LAYERS, PIECES, PIECE_BYTES, SPAN = 5, 6, 9, 40      # small and dense: most pieces overlap or touch another


def per_byte(*layers):
    """The definition: every byte of every layer into one map, later ones over earlier, then the maximal runs."""
    flat = {}
    for layer in layers:
        for at, data in (layer or {}).items():
            for offset, value in enumerate(data):
                flat[at + offset] = value
    runs, start, run = {}, None, bytearray()
    for address in sorted(flat):
        if start is not None and address == start + len(run):
            run.append(flat[address])
            continue
        if start is not None:
            runs[start] = bytes(run)
        start, run = address, bytearray([flat[address]])
    if start is not None:
        runs[start] = bytes(run)
    return runs


def _layers(rng):
    layers = []
    for _layer in range(rng.randrange(LAYERS)):
        if rng.random() < 0.1:
            layers.append(None)             # a caller's "no pokes"
            continue
        layer = {}
        for _piece in range(rng.randrange(PIECES)):
            data = bytes(rng.randrange(256) for _ in range(rng.randrange(PIECE_BYTES)))
            layer[rng.randrange(SPAN)] = data if rng.random() < 0.8 else list(data)
        layers.append(layer)
    return layers


@pytest.mark.parametrize("seed", range(4))
def test_merge_pokes_is_the_per_byte_merge_over_random_layers(seed):
    rng = random.Random(seed)
    for _round in range(ROUNDS_PER_SEED):
        layers = _layers(rng)
        merged = case.merge_pokes(*layers)
        assert merged == per_byte(*layers), layers
        assert list(merged) == sorted(merged), "the runs are keyed in address order"


def test_merge_pokes_joins_adjacent_pieces_and_keeps_a_gap():
    assert case.merge_pokes({0x10: b"\x01\x02"}, {0x12: b"\x03"}, {0x14: b"\x04"}) == {0x10: b"\x01\x02\x03", 0x14: b"\x04"}


def test_merge_pokes_of_nothing_is_nothing():
    assert case.merge_pokes() == case.merge_pokes(None, {}) == case.merge_pokes({0x10: b""}) == {}


A_STORE_AT, A_STORED_BYTE, A_POKE = 0x7000, 0x5A, {0x7002: b"\x11\x22"}


def _info(truncated=False):
    return {"regs": {"writes_truncated": truncated}, "writes": {A_STORE_AT: A_STORED_BYTE}}


def test_a_result_s_final_image_is_the_staged_one_with_the_ledger_over_it_built_at_its_first_read(monkeypatch):
    """`Result.final` is `final_image` of the run — and is NOT built until a case reads it, then kept: the cases that
    assert on the answer or the ledger alone build no sixteen-megabyte image."""
    built = []
    final_image = case.final_image
    monkeypatch.setattr(case, "final_image", lambda info, pokes: built.append(pokes) or final_image(info, pokes))
    result = case.Result(_info(), A_POKE)
    assert not built, "the image was built before anyone read it"
    expected = make_image(A_POKE)
    expected[A_STORE_AT] = A_STORED_BYTE
    assert result.final == expected and result.after(A_STORE_AT, 1) == bytes([A_STORED_BYTE]) and result.word(0x7002) == 0x1122
    assert built == [A_POKE], "the image is built once, however often it is read"


def test_a_run_whose_ledger_overflowed_is_refused_as_its_result_is_made_whoever_reads_it():
    """The refusal does not wait for a reader: an overflowed ledger fails the case at the run's end, as it did when
    the image was built there."""
    with pytest.raises(AssertionError, match="write ledger overflowed"):
        case.Result(_info(truncated=True), A_POKE)
    with pytest.raises(AssertionError, match="write ledger overflowed"):
        case.final_image(_info(truncated=True), A_POKE)
