"""Build a kit-side C probe against the oracle's OWN SOURCES, and read back what it printed.

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
import ctypes
import re
import shutil
import subprocess
import sys

from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parents[1]
SHIM = KIT / "oracle" / "shim.c"

MUSASHI = KIT / "oracle" / "musashi"
GENDIR = KIT / "oracle" / "build"
ORACLE_SRC = (MUSASHI / "m68kcpu.c", GENDIR / "m68kops.c", MUSASHI / "softfloat" / "softfloat.c",
              SHIM)


def compile_probe(probe_src, tmpdir, extra_src=()):
    """Compile `probe_src` against the oracle's sources into `tmpdir`; return the binary's path.

    ``extra_src`` adds kit sources the probe needs beyond the oracle's — the candidate-side files in
    ``src/``, for a probe that drives BOTH sides of a model in one process (test_psg_model.py).

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
         *[str(src) for src in ORACLE_SRC], *[str(src) for src in extra_src],
         str(probe_src), "-o", str(binary)],
        check=True, capture_output=True, text=True)
    return binary


# The line protocol every model probe prints (psg_model_probe.c, hw_model_probe.c), and the one
# parser for it. The two suites had a copy each, differing only in how many fields an `L` line
# carries — which is the sort of near-duplicate that quietly drifts: a probe growing a field would
# leave one parser silently dropping every ledger entry, and a ledger that parses as EMPTY compares
# equal to an expectation of `[]` on every case that has one.
#
#   K <case> <key> <value>      a scalar (a value a register held, a mask, a count)
#   L <case> <index> <field>... one ordered ledger entry; the fields are the model's own
#   F <case> <index> <value>    one byte of the model's file, by register or slot
#
# `<index>` on an `L` line is the entry's position, printed so a truncated stream is visible in the
# raw output; it is dropped here because the list's own order carries it.
_SCALAR_LINE = re.compile(r"^K (\S+) (\S+) (\d+)$", re.M)
_LEDGER_LINE = re.compile(r"^L (\S+) (\d+)((?: \d+)+)$", re.M)
_FILE_LINE = re.compile(r"^F (\S+) (\d+) (\d+)$", re.M)


# How kit.mk assembles a project's twins ($(ASM_OBJ)/$(ASM_ELF)/$(ASM_BIN)), spelt once. A suite
# that assembles its OWN probe twins must build them the way a project's are built, or it pins a
# build nobody ships — and the flags have already proved able to drift: -DRECREATE_HOST_DIFFERENTIAL
# is what selects a door stub's off-target arm, and a probe assembled without it takes the on-target
# arm and does not link. That is this module's whole reason for existing, applied to the twins.
ASM_TOOLS = ("m68k-elf-gcc", "m68k-elf-objcopy", "m68k-elf-nm")


def asm_flags(host_differential=True):
    """kit.mk's ASM_CFLAGS for the twins, minus the project include paths a probe has none of.

    `host_differential=False` drops the OFF-TARGET marker, giving the flag set a project's own
    target build assembles with. Only a case that pins the two builds against each other has any use
    for it; everything else wants the default, which is what `make test` really runs.
    """
    flags = ["-m68000", "-nostdlib", *_asm_twin().asm_door_flags().split()]
    if host_differential:
        flags.append("-DRECREATE_HOST_DIFFERENTIAL")
    return tuple(flags)


def assemble_twins(source, out_dir, name="twins", flags=None):
    """Assemble one `.S` source string into `<out_dir>/<name>.{elf,bin}`, as kit.mk does.

    Returns `out_dir`, which is what `AsmTwins` takes — so a suite writes its probe assembly, calls
    this, and hands the result straight over.

    Skips the calling suite when the cross toolchain is absent, this directory's convention for a
    build product that may simply not be installed.
    """
    asm_twin = _asm_twin()
    for tool in ASM_TOOLS:
        if shutil.which(tool) is None:
            pytest.skip(f"{tool} is not installed, so the probe twins cannot be assembled",
                        allow_module_level=True)
    out_dir = Path(out_dir)
    asm = out_dir / f"{name}.S"
    obj, elf, binary = out_dir / f"{name}.o", out_dir / f"{name}.elf", out_dir / f"{name}.bin"
    asm.write_text(source)
    flags = list(asm_flags() if flags is None else flags)
    _run(["m68k-elf-gcc", *flags, "-c", str(asm), "-o", str(obj)])
    # -Wl,-e0 and --build-id=none for kit.mk's reasons: the blob has no `_start`, and a build-id note
    # would be carried into the flat binary and move every symbol after it.
    _run(["m68k-elf-gcc", *flags, "-Wl,--build-id=none", "-Wl,-e0",
          f"-Wl,-Ttext={asm_twin.asm_link_base()}", str(obj), "-o", str(elf)])
    _run(["m68k-elf-objcopy", "-O", "binary", str(elf), str(binary)])
    return out_dir


def build_host_lib(source, out_dir, name):
    """Compile one C source into a shared library and return the loaded ctypes handle.

    A stand-in for a project's candidate `.so`, for a suite whose subject is something the harness
    does WITH that library rather than the library itself (test_callback_door.py's host "cores").
    """
    if shutil.which("cc") is None:
        pytest.skip("no C compiler, so the host stand-in cannot be built", allow_module_level=True)
    lib = Path(out_dir) / name
    _run(["cc", "-std=c11", "-O0", "-fPIC", "-shared", str(source), "-o", str(lib)])
    return ctypes.CDLL(str(lib))


def _run(argv):
    subprocess.run(argv, check=True, capture_output=True, text=True)


def _asm_twin():
    """`recreate_kit.asm_twin`, imported on demand.

    Not at module scope: this file is imported by suites that bind no project and never touch the
    twins, and `tools/` is only on `sys.path` once something has put it there. The one caller that
    needs it is the one that also needs the toolchain.
    """
    sys.path.insert(0, str(KIT.parent))
    from recreate_kit import asm_twin        # noqa: E402  (importable only after the path insert)
    return asm_twin


def run_probe(binary):
    """Run a built model probe and return ``{case: {"scalars", "ledger", "file"}}``.

    ``ledger`` entries are tuples of whatever fields the probe printed, in order — three for the PSG
    model's ``(kind, reg, value)``, two for the hardware model's ``(slot, value)`` — so the shape is
    the model's own and this parser does not have to know which model it is reading.
    """
    out = subprocess.run([str(binary)], check=True, capture_output=True, text=True).stdout
    cases = {}

    def case(name):
        return cases.setdefault(name, {"scalars": {}, "ledger": [], "file": {}})

    for name, key, value in _SCALAR_LINE.findall(out):
        case(name)["scalars"][key] = int(value)
    for name, _index, fields in _LEDGER_LINE.findall(out):
        case(name)["ledger"].append(tuple(int(field) for field in fields.split()))
    for name, index, value in _FILE_LINE.findall(out):
        case(name)["file"][int(index)] = int(value)
    return cases
