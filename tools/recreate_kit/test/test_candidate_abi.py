"""Pin `harness._HW_LEDGER_ABI` against the surface `include/hw.h` actually declares.

The list is a PRESENCE PROBE: a candidate `.so` that exports every name on it is taken to be a
current build, its `g_*` functions are bound with argtypes and called. So the list is only as good
as its youngest symbol — and the hole it left is not theoretical. `g_io_reset` grew a fourth
argument (the write-through column) without any NEW name joining the list, so a project `.so` built
before that change still exported all six `g_io_*` names, still passed the probe, and was then
called with four arguments for a three-argument function: a SIGSEGV inside the candidate, with
nothing naming the rebuild that answers it.

Adding `g_io_writeback_count` closed that instance. This closes the CLASS, by deriving the expected
names rather than trusting anyone to remember: a `g_io_*` / `g_hw_*` surface added to `hw.h` and not
to the list reds here, at the commit that adds it, which is the moment the author is in a position to
decide whether it should be probed or deliberately left out.

TWO SOURCES, BOTH CHECKED. `hw.h` says what the harness is meant to drive (its own "what the harness
drives" section); `nm -gU` on the built candidate says what a build really exports. A name in the
header that the `.so` does not define would be the stale build the probe exists to catch, so that
direction is asserted too.

Why the header and not `nm` alone: the smoke candidate's `.so` also holds `kit_candidate.c`'s
reconstruction cores, which are named after the model they exercise (`g_io_reads_the_pair`,
`g_hw_writes_the_three`, ...) and share the prefixes. They are not ABI — they are a test fixture's
routines — so the prefix alone cannot separate them from the ledger's surface.

`nm -gU` (GLOBAL, DEFINED symbols only) rather than `hasattr(_lib, name)`, which is
projects/wonderboy/recreate/test/leaf.py's finding: a `ctypes.CDLL` handle resolves through the
whole process's namespace, so `hasattr` answers True for libc as readily as for the candidate.
"""
import re
import subprocess

from pathlib import Path

import pytest

from kit_smoke_project import bind

harness = bind()

KIT = Path(__file__).resolve().parents[1]
HW_HEADER = KIT / "include" / "hw.h"

# The prefixes the harness probes as ONE group. `hw_read8` / `io_read8` and the rest of the
# CALL-IN surface are deliberately outside it: those are what a reconstruction calls, not what the
# harness drives, and their absence is a link error in the candidate rather than a stale-probe hole.
PROBED_PREFIXES = ("g_io_", "g_hw_")
# A function declaration in hw.h, as `<return type> <name>(`. The header declares nothing else at
# file scope, so this needs no more grammar than that.
_DECLARATION = re.compile(r"^[A-Za-z_][\w *]*?\b(g_(?:io|hw)_\w+)\s*\(", re.MULTILINE)


def _declared_surface():
    """The `g_io_*` / `g_hw_*` functions `include/hw.h` declares — the harness-driven ABI."""
    names = set(_DECLARATION.findall(HW_HEADER.read_text()))
    assert names, f"{HW_HEADER} declares no {'/'.join(PROBED_PREFIXES)}* function — this pin is " \
                  f"matching nothing, so it would go green on an empty header"
    return names


def _exported_symbols():
    """The names the candidate `.so` itself DEFINES, read with `nm -gU`.

    Mach-O prefixes a leading underscore and ELF does not, so both spellings are accepted.
    """
    out = subprocess.run(["nm", "-gU", str(harness.LIB)], capture_output=True, text=True)
    if out.returncode != 0:
        pytest.skip(f"nm could not read {harness.LIB}: {out.stderr.strip()}")
    names = set()
    for line in out.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[-2] in ("T", "t", "D", "B"):
            names.add(parts[-1].lstrip("_"))
    return names


def test_every_declared_ledger_symbol_is_in_the_probed_list():
    """The pin itself. A `g_io_*`/`g_hw_*` declaration missing from `_HW_LEDGER_ABI` is a probe that
    cannot tell the build that has it from the build that does not."""
    missing = sorted(_declared_surface() - set(harness._HW_LEDGER_ABI))
    assert not missing, (
        f"include/hw.h declares {', '.join(missing)}, which harness._HW_LEDGER_ABI does not probe. "
        f"A candidate built before they existed passes the probe anyway and is then driven as though "
        f"it had them — which is the stale-.so SIGSEGV this file's header describes. Add them to "
        f"the list, or say in a comment there why this one is deliberately unprobed")


def test_the_probed_list_is_what_a_current_build_really_exports():
    """...and the other direction, which is the probe doing its job: every name on the list is a
    symbol `src/hw.c` defines, so a red here is a stale or half-linked candidate rather than a list
    that has drifted."""
    unexported = sorted(set(harness._HW_LEDGER_ABI) - _exported_symbols())
    assert not unexported, (
        f"{harness.LIB} exports none of {', '.join(unexported)}, which harness._HW_LEDGER_ABI "
        f"probes for — the candidate did not link tools/recreate_kit/src/hw.c, or was built before "
        f"those symbols existed")


def test_the_newest_symbol_really_is_the_one_that_dates_the_build():
    """`g_io_writeback_count` is the name that separates a candidate holding the write-through
    COLUMN from one whose `g_io_reset` takes three arguments. Pinned as a named fact rather than
    left implicit in the list's order, because the list's order is a comment and this is a test."""
    assert "g_io_writeback_count" in harness._HW_LEDGER_ABI
    assert "g_io_writeback_count" in _declared_surface()
    assert "g_io_writeback_count" in _exported_symbols()
