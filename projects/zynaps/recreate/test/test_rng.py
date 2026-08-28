"""Differential tests for rand16 @ 0x13bf8 (src/rng.c)."""
import ctypes
import random

import pytest

import harness
from harness import differential, report

ENTRY_RAND16 = 0x13bf8

A_RNG_LFSR_STATE = 0x195f4     # mirror of include/rng.h
SHIPPED_SEED = 0x83e4f2b3  # what the .PRG's own text holds at A_RNG_LFSR_STATE before anything runs

harness._lib.g_rand16.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_rand16.restype = ctypes.c_uint32


def _rng_case(seed, poison=False):
    """Run the generator with A_RNG_LFSR_STATE holding `seed` (None = the image's shipped value)."""
    pokes = {} if seed is None else {A_RNG_LFSR_STATE: seed.to_bytes(4, "big")}
    diffs, info = differential(ENTRY_RAND16, {"_pokes": pokes},
                               lambda lib, buf: lib.g_rand16(buf), poison=poison)
    assert not diffs, f"seed={seed}\n{report(diffs)}"
    # The word itself is returned in D0, which the image diff cannot see, so compare it directly.
    # The comparison is over the WHOLE longword, but only its low half is a two-sided check: the
    # candidate returns a uint16_t, so its high half is zero by construction and no reconstruction
    # expressible through this glue can fail that part. The original's `moveq #0,d0` is asserted on
    # the ORACLE side only.
    assert info["ret"] == info["regs"]["d0"], (
        f"seed={seed}: word cand={info['ret']:#x} oracle={info['regs']['d0']:#x}")
    return info["ret"]


def test_shipped_seed():
    """The state the binary ships with, untouched — the very first draw the game ever makes.

    SHIPPED_SEED is pinned against the image itself rather than against a second draw: the routine
    maps 32 state bits to a 16-bit word, so 65,536 states share any given output and comparing two
    draws would leave a wrong constant undetected. It is load-bearing for the two tests below.
    """
    assert int.from_bytes(harness.BASE_IMAGE[A_RNG_LFSR_STATE:A_RNG_LFSR_STATE + 4], "big") == SHIPPED_SEED
    _rng_case(None)


@pytest.mark.parametrize("seed", (0, 1, 2, 0x80000000, 0xffffffff, 0x7fffffff, 0x1d872b41))
def test_edge_seeds(seed):
    """Both absorbing-looking extremes plus the tap mask itself.

    A seed of 0 is the LFSR's fixed point: no bit ever leaves the top, so the state stays 0 and the
    word is 0 — and the case is worth keeping because a candidate that seeded `result` wrong, or
    folded the tap in on the wrong sense of the carry, breaks here first.
    """
    _rng_case(seed)


def test_attribution():
    """Poison the state longword and re-run: a candidate that never writes it back stays canary.

    Safe here even though the state is a read-modify-write: `_attribution_check` re-runs BOTH cores
    on the poisoned image, so the inverted input is the same input on both sides — a different draw
    from the sequence, compared just as strictly.
    """
    for seed in (SHIPPED_SEED, 0, 0xffffffff, 0x12345678):
        _rng_case(seed, poison=True)


def test_state_advances_sixteen_steps():
    """Sixteen single-bit steps, not one: the word's bits are the sixteen carries, in order.

    Reproduces the Galois step independently in Python and checks both outputs against it, so a
    candidate and an oracle that agreed on a WRONG step count could not both slip through.
    """
    seed = SHIPPED_SEED
    for _ in range(8):
        state, expected = seed, 0
        for _ in range(16):
            bit_out = state >> 31
            state = ((state << 1) & 0xffffffff) ^ (0x1d872b41 if bit_out else 0)
            expected = ((expected << 1) | bit_out) & 0xffff
        assert _rng_case(seed) == expected, f"seed={seed:#x}"
        seed = state


FUZZ_CHUNKS = 4
FUZZ_CASES = 400


def _fuzz_seeds():
    rng = random.Random(0x13BF8)                 # seeded ONCE — every chunk replays this stream
    for i in range(FUZZ_CASES):
        yield i, rng.randrange(1 << 32)


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_fuzz(chunk):
    for i, seed in _fuzz_seeds():
        if i % FUZZ_CHUNKS == chunk:
            _rng_case(seed)


# --- test_constants.py collects these; see README.md, "Adding a function" ---
MIRRORS = (("A_RNG_LFSR_STATE", "include/rng.h", "A_rng_lfsr_state"),)
ENTRY_PROLOGUES = {"ENTRY_RAND16": "48e70f002a39000195f4"}
