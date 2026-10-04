"""`case.merge_pokes` held to its definition: poke dicts laid over each other BYTE BY BYTE, later layers winning, as one
dict of maximal runs. The module builds the answer run-wise (the extents, then a slice store per piece); the reference
here is the definition spelt per byte, and the two are held equal over random layers — overlapping, adjacent, empty,
bytes and lists of ints alike."""
import random

import pytest

import case

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
