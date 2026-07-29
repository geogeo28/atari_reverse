"""Differential tests for make_fill_pattern @ 0x102fe and fill_pattern_n @ 0x10334 (src/fill.c)."""
import ctypes
import random

import pytest

import abi
import harness
from harness import differential, hi_garbage, report

ENTRY_MAKE_FILL_PATTERN = 0x102fe
ENTRY_FILL_PATTERN_N = 0x10334

CELL_BYTES = 8            # bytes per 4-plane cell (mirror of include/joust.h)
FILL_DST = 0x30000        # scratch destination: clear of the program and of abi.STUB/ARG_BLOCK,
                          # with room below the staged-file table (0xbf000) for a 512 KiB fill
INSNS_PER_PASS = 4        # move.l, move.l, subq.w, bne — the loop body, for sizing the oracle cap
JUNK_D1, JUNK_D2 = 0xdeadbeef, 0xfeedface   # pre-loaded so `clr.l d1` / `clr.l d2` have to happen

harness._lib.g_make_fill_pattern.argtypes = [ctypes.POINTER(ctypes.c_uint8),
                                             ctypes.c_uint32, ctypes.c_uint32]
harness._lib.g_make_fill_pattern.restype = None
harness._lib.g_fill_pattern_n.argtypes = [ctypes.POINTER(ctypes.c_uint8)] + [ctypes.c_uint32] * 4
harness._lib.g_fill_pattern_n.restype = ctypes.c_uint32


# ---------------------------------------------------------------- make_fill_pattern

def _pattern_case(colour, poison=False):
    """Call make_fill_pattern(D0 = colour) through the stub that stores D1/D2 at A0."""
    pokes = abi.register_call_pokes(ENTRY_MAKE_FILL_PATTERN)
    pokes[abi.RESULT] = bytes(range(0x71, 0x79))     # neither output value, so silence shows up
    regs = {"d0": colour, "d1": JUNK_D1, "d2": JUNK_D2, "a0": abi.RESULT, "_pokes": pokes}
    diffs, _ = differential(abi.STUB, regs,
                            lambda lib, buf: lib.g_make_fill_pattern(buf, colour, abi.RESULT),
                            poison=poison)
    assert not diffs, f"colour={colour:#x}\n{report(diffs)}"


def test_make_fill_pattern_all_colour_bytes():
    """Every colour byte. Only bit 0 may matter — the other seven are the degeneracy under test."""
    for colour in range(0x100):
        _pattern_case(colour)


def test_make_fill_pattern_attribution():
    # `btst #0,d0` is a LONGWORD test on a data register, so bits above the byte are read too (and
    # ignored). poison=True here also proves the candidate writes both result longwords, including
    # the D2 half the original clears and never touches again.
    for colour in (0, 1, 0xfe, 0xff, 0x100, 0x101, 0x12345678, 0x12345679, 0xfffffffe, 0xffffffff):
        _pattern_case(colour, poison=True)


def test_make_fill_pattern_fuzz():
    rng = random.Random(0x102FE)
    for _ in range(400):
        _pattern_case(rng.randrange(1 << 32))


# ---------------------------------------------------------------- fill_pattern_n

def _fill_case(count, planes01, planes23, seed, dst=FILL_DST, poison=False):
    """Call fill_pattern_n(D0 = count, D1/D2 = pattern, A0 = dst) at its own entry."""
    passes = ((count - 1) & 0xffff) + 1                       # `subq.w`: a count of 0 means 65536
    rng = random.Random(seed)
    pokes = {dst: bytes(rng.randrange(256) for _ in range(passes * CELL_BYTES))}
    regs = {"d0": count, "d1": planes01, "d2": planes23, "a0": dst, "_pokes": pokes}
    diffs, info = differential(
        ENTRY_FILL_PATTERN_N, regs,
        lambda lib, buf: lib.g_fill_pattern_n(buf, dst, count, planes01, planes23),
        max_insns=passes * INSNS_PER_PASS + 100, poison=poison)
    assert not diffs, f"count={count:#x} pattern={planes01:#x}/{planes23:#x}\n{report(diffs)}"
    # A0 is left one past the last cell written; the reconstruction returns the same end pointer.
    assert info["ret"] == info["regs"]["a0"], (
        f"count={count:#x}: end ptr cand={info['ret']:#x} oracle={info['regs']['a0']:#x}")


_FILL_PATTERNS = ((0, 0), (0xffff0000, 0), (0xffffffff, 0xffffffff), (0x0f0f0f0f, 0xf0f0f0f0))


@pytest.mark.parametrize("count", (1, 2, 3, 0xff, 0x100, 0x101, 0x1000, 0xfffe, 0xffff))
def test_fill_pattern_n_counts(count):
    for seed, (planes01, planes23) in enumerate(_FILL_PATTERNS):
        _fill_case(count, planes01, planes23, seed=seed)


def test_fill_pattern_n_attribution():
    # Seeded destinations already differ from the pattern, but poison also catches a candidate that
    # writes fewer cells than the original by leaving the tail canaries in place.
    for count in (1, 2, 0xff, 0x100):
        _fill_case(count, 0xffff0000, 0, seed=count, poison=True)


def test_fill_pattern_n_count_high_half_ignored():
    """`subq.w #1,d0` counts the word, so garbage above it must not change the pass count."""
    rng = random.Random(0x10334)
    for low in (1, 2, 0xff, 0x100, 0xffff):
        _fill_case(hi_garbage(rng, low), 0x0f0f0f0f, 0xf0f0f0f0, seed=low)


def test_fill_pattern_n_zero_count_is_the_full_word():
    """A count of 0 runs the loop 65536 times (0 -> 0xffff -> ... -> 0), filling 512 KiB.

    Kept to a single case: it is ~262k oracle instructions, well past the harness's default cap,
    and it is the only input for which the `subq.w`/`bne` wrap is observable.
    """
    _fill_case(0, 0xffff0000, 0, seed=0)


FUZZ_CHUNKS = 4


def _fuzz_cases():
    rng = random.Random(0x51FF)                  # seeded ONCE — every chunk replays this stream
    for i in range(400):
        yield (i, rng.randrange(1, 0x400), rng.randrange(1 << 32), rng.randrange(1 << 32),
               rng.randrange(1 << 32))


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_fuzz(chunk):
    for i, count, planes01, planes23, colour in _fuzz_cases():
        if i % FUZZ_CHUNKS != chunk:
            continue
        _fill_case(count, planes01, planes23, seed=i)
        _pattern_case(colour)
