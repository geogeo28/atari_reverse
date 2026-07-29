"""Differential tests for rng_advance @ 0x105c2 (src/rng.c)."""
import ctypes
import random

import pytest

import harness
from harness import differential, report, hi_garbage

ENTRY_RNG_ADVANCE = 0x105c2
A_RNG_PTR = 0x10dfe      # names.txt: rng_ptr
RNG_LIMIT = 0x17832      # the RELOCATED `cmpi.l #$17832` — the listing shows the raw 0x7832
RNG_RESET = 0x10000      # the RELOCATED `move.l #$10000` — the listing shows a raw 0

harness._lib.g_rng_advance.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32]
harness._lib.g_rng_advance.restype = ctypes.c_uint32


def _case(cursor, mix, poison=False):
    """One rng_advance call: rng_ptr = cursor, D0 = mix."""
    regs = {"d0": mix, "_pokes": {A_RNG_PTR: cursor.to_bytes(4, "big")}}
    diffs, info = differential(ENTRY_RNG_ADVANCE, regs,
                               lambda lib, buf: lib.g_rng_advance(buf, mix), poison=poison)
    assert not diffs, f"cursor={cursor:#x} mix={mix:#x}\n{report(diffs)}"
    # The wrap path is bracketed by `move.l d0,-(a7)` / `move.l (a7)+,d0`: callers keep D0. The
    # reconstruction states that by returning `mix` unchanged, so this pins the ORACLE's half of
    # the contract — it fails if the original ever leaves D0 clobbered, not if the C drifts.
    assert info["ret"] == info["regs"]["d0"], (
        f"cursor={cursor:#x} mix={mix:#x}: D0 cand={info['ret']:#x} oracle={info['regs']['d0']:#x}")


# Cursors straddling every decision the routine makes: the step across the wrap threshold, the
# 32-bit wrap of `addq.l`, and the sign flip that makes the SIGNED `blt` refuse to wrap.
_EDGE_CURSORS = (
    0, RNG_RESET, RNG_RESET + 2,
    RNG_LIMIT - 4, RNG_LIMIT - 2, RNG_LIMIT, RNG_LIMIT + 2,   # step to just under / onto / past
    0x7ffffffc, 0x7ffffffe,                                   # +2 crosses into "negative"
    0x80000000, 0xfffffffe, 0xffffffff,                       # negative, and the longword wrap
)
# Mixes covering the `andi.l #$fe` mask: below it, on it, and with every bit outside it set.
_EDGE_MIXES = (0, 1, 2, 0xfe, 0xff, 0x100, 0x1ff, 0xffff, 0xfffffffe, 0xffffffff)


@pytest.mark.parametrize("cursor", _EDGE_CURSORS)
def test_edge_cursors(cursor):
    # poison=True: rng_ptr is the only byte written, so a candidate that never wrote it would
    # otherwise pass whenever the pre-poked cursor happens to equal the result.
    for mix in _EDGE_MIXES:
        _case(cursor, mix, poison=True)


def test_mix_high_half_ignored():
    """`andi.l #$fe` keeps one byte of D0, so garbage above it must not reach rng_ptr."""
    rng = random.Random(0x5C2)
    for low in (0x00, 0x01, 0x7e, 0x7f, 0x80, 0xfe, 0xff):
        # Force the wrap path (cursor at the limit) so the mix is actually consumed.
        _case(RNG_LIMIT - 2, hi_garbage(rng, low), poison=True)


FUZZ_CHUNKS = 4


def _fuzz_cases():
    rng = random.Random(0x105C2)                 # seeded ONCE — every chunk replays this stream
    for i in range(600):
        # Half the cursors land near the threshold, where the interesting branch lives; the rest
        # roam the whole 32-bit range, including the negative half the signed compare cares about.
        near = rng.random() < 0.5
        cursor = (RNG_LIMIT + rng.randrange(-0x40, 0x40)) if near else rng.randrange(1 << 32)
        yield i, cursor & 0xffffffff, rng.randrange(1 << 32)


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_fuzz(chunk):
    for i, cursor, mix in _fuzz_cases():
        if i % FUZZ_CHUNKS == chunk:
            _case(cursor, mix)
