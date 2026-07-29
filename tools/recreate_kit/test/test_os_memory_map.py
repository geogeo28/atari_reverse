"""Cross-language pin: the TOS model's memory map must agree between C and Python.

``tools/recreate_kit/include/os.h`` (compiled into both the oracle shim and every reconstruction's
OS wrappers) and ``tools/recreate_kit/harness.py`` (which stages files into the image from Python)
each declare the staged-file table layout and the modeled Malloc base. CLAUDE.md §5 requires one
canonical definition with the other pinned equal by a test; C and Python cannot import each other,
so this parses both sources textually.

Drift here is not loud on its own: os_fopen would simply look at a table address the harness never
wrote and report "file not staged", or Malloc would hand out a block the harness thinks is free.
Both sources are parsed rather than imported because ``harness`` needs a bound project and a built
candidate ``.so``; this test must run in a bare checkout.
"""
import re
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
OS_H = KIT / "include" / "os.h"
# The Python mirror is split across two files: harness.py holds the file-staging map it pokes into
# the image, and oracle/emu.py holds OS_HEAP_BASE, which its per-run Malloc guard needs. Each
# constant must be defined in exactly one of them (asserted below) so there is still one source.
PY_MIRRORS = (KIT / "harness.py", KIT / "oracle" / "emu.py")

# Every constant that exists on both sides. os.h is the canonical definition.
PINNED = ("OS_HEAP_BASE", "OS_FS_TABLE", "OS_FS_STAGING", "OS_FS_ENTRY", "OS_FS_NAME",
          "OS_FS_FIRST_HANDLE", "OS_DOSOUND_LOG_MAX")


def _c_defines(source, names):
    """{name: value} for `#define <name> <int literal>` (an optional u/U suffix), for `names`."""
    found = {}
    for name in names:
        m = re.search(rf"^#define\s+{name}\s+(0x[0-9a-fA-F]+|\d+)[uU]?\b", source, re.M)
        if m:
            found[name] = int(m.group(1), 0)
    return found


def _py_constants(source, names):
    """{name: value} for module-level `<name> = <int literal>` assignments, for `names`."""
    found = {}
    for name in names:
        m = re.search(rf"^{name}\s*=\s*(0x[0-9a-fA-F]+|\d+)\b", source, re.M)
        if m:
            found[name] = int(m.group(1), 0)
    return found


def test_python_mirror_matches_os_h():
    c = _c_defines(OS_H.read_text(), PINNED)
    per_file = {path: _py_constants(path.read_text(), PINNED) for path in PY_MIRRORS}
    py, home = {}, {}
    for path, found in per_file.items():
        for name, value in found.items():
            assert name not in py, (
                f"{name} is defined in both {home[name].name} and {path.name} — the Python mirror "
                f"must have one source per constant, or the two copies can drift apart")
            py[name], home[name] = value, path

    assert set(c) == set(PINNED), f"os.h is missing/unparsable for: {sorted(set(PINNED) - set(c))}"
    assert set(py) == set(PINNED), (
        f"{'/'.join(p.name for p in PY_MIRRORS)} is missing/unparsable for: "
        f"{sorted(set(PINNED) - set(py))}")

    drift = {n: (c[n], py[n]) for n in PINNED if c[n] != py[n]}
    assert not drift, (
        "os.h and the Python mirror disagree on the TOS model's memory map:\n"
        + "\n".join(f"  {n}: os.h={cv:#x} {home[n].name}={pv:#x}"
                    for n, (cv, pv) in drift.items()))


def test_staged_file_table_fits_below_staging():
    """The table must hold OS_FS_SLOTS entries without running into the staging area below it."""
    c = _c_defines(OS_H.read_text(), PINNED + ("OS_FS_SLOTS",))
    table_bytes = c["OS_FS_SLOTS"] * c["OS_FS_ENTRY"]
    assert c["OS_FS_TABLE"] + table_bytes <= c["OS_FS_STAGING"], (
        f"the {c['OS_FS_SLOTS']}-entry staged-file table at {c['OS_FS_TABLE']:#x} "
        f"({table_bytes} bytes) overruns OS_FS_STAGING at {c['OS_FS_STAGING']:#x}")
