"""Cross-check the deterministic trap model (shim.c + os.h) against a genuine TOS ROM running
under Hatari (oracle/tos_probe.py). This is the real-hardware anchor behind the shim-contract
tests in test_os.py: it proves the semantics we hand-model actually match a real GEMDOS.

Two kinds of claim (see oracle/tos_probe.py):
  * exact-value  — Getrez (low-res == 0) and sequential Fread (byte-exact data + cursor/EOF
    counts) must match the shim to the byte.
  * invariant    — Malloc rounds an odd request up to an even, non-overlapping block. The shim
    honors the same rule; only the concrete base is deliberately fixed (OS_HEAP_BASE) so the
    differential harness stays deterministic — real TOS returns a machine-dependent address.

Skips (does not fail) when Hatari or a TOS ROM isn't installed — the ROM isn't redistributable,
so this can't be a hard dependency of `make test`. The pure shim-contract tests in test_os.py
cover the same semantics without it.
"""
import pytest

import harness                          # noqa: F401  — inserts oracle/ onto sys.path
import tos_probe                        # from oracle/
from tos_probe import MALLOC_A, READ_SIZES, LOW_RES, PROBE_INPUT

# Mirror of os.h: the shim's fixed Malloc base and its even-rounding rule. Kept here (not
# imported from C) precisely so a drift between os.h and this expectation fails the test.
OS_HEAP_BASE = 0x20000


def _round_up_even(n):
    return (n + 1) & ~1


def _expected_read_counts(file_len):
    """The cursor/EOF model os_fread implements: each read returns min(request, remaining)."""
    counts, cursor = [], 0
    for request in READ_SIZES:
        got = max(0, min(request, file_len - cursor))
        counts.append(got)
        cursor += got
    return tuple(counts)


pytestmark = pytest.mark.skipif(
    not tos_probe.available(),
    reason="real-TOS cross-check needs Hatari + a TOS ROM (see oracle/tos_probe.py)")


def test_shim_semantics_match_real_tos():
    cap = tos_probe.capture()

    # --- exact-value calls: the shim must equal real TOS to the byte ---
    assert cap["rez"] == LOW_RES, "Getrez in low-res is 0, as the shim returns for 0x04"
    assert cap["counts"] == _expected_read_counts(len(PROBE_INPUT)), \
        "sequential Fread must advance the cursor and return 0 past EOF (os_fread)"
    assert cap["read"] == PROBE_INPUT, "Fread must return the file's bytes, as os_fread copies from staging"

    # --- Malloc invariant: even-aligned, non-overlapping, odd request rounded up to even ---
    # This is the property the shim's bump allocator relies on; only the base address differs
    # (real TOS is machine-dependent, the shim fixes it at OS_HEAP_BASE for determinism).
    assert cap["ptr1"] % 2 == 0 and cap["ptr2"] % 2 == 0, "Malloc blocks are even-aligned"
    gap = cap["ptr2"] - cap["ptr1"]
    assert gap >= MALLOC_A, "the second block must not overlap the first"
    assert gap == _round_up_even(MALLOC_A), \
        "real TOS rounds the odd request up to even — matching the shim's (n + 1) & ~1"

    # Pin the shim's own base to os.h so this documents (and guards) the deliberate divergence.
    assert OS_HEAP_BASE % 2 == 0, "the shim's fixed Malloc base honors the same even-alignment"
