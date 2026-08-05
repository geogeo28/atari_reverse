"""Build a kit-side C probe against the oracle's OWN SOURCES.

Two suites here reach the oracle from C rather than from Python (`test_entry_state.py`,
`test_reported_regs.py`): this directory deliberately binds no project, and `harness`/`emu` both
load a candidate `.so` at import, so the oracle cannot be reached from Python here at all. Both need
the identical build, and it lives here because two files carrying it could disagree about the flags.

Compiling the oracle's sources rather than linking the shared `liboracle.so` is what keeps those
suites honest: `shim.c` is recompiled on every run, so a reverted property reddens immediately
instead of hiding behind an up-to-date-looking artifact (the mtime relink trap). The generated
opcode table and the Musashi clone are gitignored build products; without them there is nothing to
compile, so a suite skips rather than fails.
"""
import subprocess

from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parents[1]
SHIM = KIT / "oracle" / "shim.c"

MUSASHI = KIT / "oracle" / "musashi"
GENDIR = KIT / "oracle" / "build"
ORACLE_SRC = (MUSASHI / "m68kcpu.c", GENDIR / "m68kops.c", MUSASHI / "softfloat" / "softfloat.c",
              SHIM)


def compile_probe(probe_src, tmpdir):
    """Compile `probe_src` against the oracle's sources into `tmpdir`; return the binary's path.

    Skips the calling suite when a source is absent — the build products are gitignored, so a bare
    checkout is the only way that happens.
    """
    missing = [str(src) for src in ORACLE_SRC if not src.exists()]
    if missing:
        pytest.skip(f"the oracle's sources are not built here ({', '.join(missing)}) — "
                    f"run a project's `make oracle` first")
    binary = Path(tmpdir) / "probe"
    # -O0 because this compiles ~800 KiB of generated opcode table on every run and the optimiser
    # changes nothing a probe asks about; -DM68K_EMULATE_TRACE=0 mirrors kit.mk's OCFLAGS, which
    # shim.c refuses to build without.
    subprocess.run(
        ["cc", "-O0", "-DM68K_EMULATE_TRACE=0",
         f"-I{KIT / 'include'}", f"-I{MUSASHI}", f"-I{GENDIR}", f"-I{MUSASHI / 'softfloat'}",
         *[str(src) for src in ORACLE_SRC], str(probe_src), "-o", str(binary)],
        check=True, capture_output=True, text=True)
    return binary
