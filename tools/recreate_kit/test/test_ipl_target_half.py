"""`ipl.h`'s TARGET half, compiled: the two instructions each door emits, and their order.

THE DOOR HAS NO OTHER SURFACE. Off target `include/ipl.h` is a no-op — the oracle enters every run at
IPL 7, takes no interrupts and reports no SR — so the Tier 1 differential stays green if a core's
whole bracket vanishes, which that header says in its own words. What normally stands in for it is
TIER 3: the pair costs real 68000 cycles, so a project pins the row (`bench/tier3.py` over
`xbios_giaccess`). That instrument fails for exactly one shape of routine — one whose ROM body does
not TERMINATE without an interrupt. TOS's `Vsync` is the worked case: `emu.run_bench`, Tier 3's
numerator door, has no scheduled-write door, so the m68k build's own spin could never be released and
the routine has no priced row at all. Its `os_ipl_unmask` is then pinned by nothing.

So this pins the SHAPE instead, at the only place the target half is real: the compiler. Each project
that ships an `atari/shim_include/ipl.h` is compiled here with `m68k-elf-gcc -S`, and the emitted
instructions are read back — that `os_ipl_unmask` is `move.w %sr,<d>` followed by
`andi.w #0xf8ff,%sr`, IN THAT ORDER, and that `os_ipl_raise` is the same save followed by
`ori.w #0x0700,%sr`. It is a weaker claim than a cycle count and it is the cheapest one that is not
nothing: it catches a door emptied to a no-op, one whose mask constant moved, one that dropped the
save the restore needs, and the transposition — `andi` before the `move.w sr`, which reads back a
mask the routine has already cleared and restores the WRONG interrupt level to the caller.

WHAT IT DELIBERATELY DOES NOT CLAIM: that a core CALLS the door. Nothing here compiles a core. That
is the hole Tier 3 fills where a routine can be priced, and `test_xbios_vsync.py`'s docstring records
it for the one routine where it cannot.

Game-agnostic, as every kit suite is: the projects are discovered, not named, and a tree with none is
a skip rather than a failure.
"""
import re
import shutil
import subprocess

from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parents[1]
PROJECTS = KIT.parents[1] / "projects"
# Where a project puts the half that shadows the kit's on the include path (`include/ipl.h`, "ON
# TARGET"). A project with no target build has no such file and is simply not a case here.
TARGET_HALF = Path("recreate") / "atari" / "shim_include" / "ipl.h"

# The shipped ROM builds compile for a bare 68000 with no libc; nothing below depends on the
# optimisation level, but -O2 is what a project's own target.mk uses and an inline asm block that
# survives it is the one the machine runs.
COMPILE_FLAGS = ("-m68000", "-O2", "-S", "-ffreestanding", "-nostdlib")

# One probe function per door, so the emitted instructions can be attributed to the door that made
# them rather than found somewhere in a single blob. `os_ipl_t` is the header's own typedef; each
# probe returns the saved word so that nothing can be optimised away as dead.
PROBE_SOURCE = """#include "ipl.h"

os_ipl_t probe_raise(void) { return os_ipl_raise(); }
os_ipl_t probe_unmask(void) { return os_ipl_unmask(); }
void probe_restore(os_ipl_t saved) { os_ipl_restore(saved); }
"""

# `move.w %sr,<any data register>` — the save both doors open with, and the value `os_ipl_restore`
# puts back. GCC substitutes the register into the header's own template, so the register itself is
# its choice and not a claim.
SAVE = r"move\.w\s+%sr\s*,\s*%d[0-7]"
RESTORE = r"move\.w\s+%d[0-7]\s*,\s*%sr"
# ...and the masks, which are the ROM's own immediates: $700 sets IPL 7, $f8ff clears the field.
RAISE_MASK = r"ori\.w\s+#(?:0x0*700|1792)\s*,\s*%sr"
UNMASK_MASK = r"andi\.w\s+#(?:0x0*f8ff|63743|-1793)\s*,\s*%sr"

TARGET_HALVES = sorted(path for path in PROJECTS.glob(f"*/{TARGET_HALF}")) if PROJECTS.is_dir() \
    else []


@pytest.fixture(scope="module", params=[pytest.param(path, id=path.parents[2].name)
                                        for path in TARGET_HALVES])
def emitted(request, tmp_path_factory):
    """The assembly one project's target half compiles to, as {probe name: [instruction, ...]}."""
    if shutil.which("m68k-elf-gcc") is None:
        pytest.skip("m68k-elf-gcc is not installed; compiling the header is what this pins")
    header = request.param
    out = tmp_path_factory.mktemp(f"ipl_{header.parents[2].name}")
    source = out / "probe.c"
    source.write_text(PROBE_SOURCE)
    subprocess.run(["m68k-elf-gcc", *COMPILE_FLAGS, f"-I{header.parent}", str(source),
                    "-o", str(out / "probe.s")], check=True)
    return _by_function((out / "probe.s").read_text())


def _by_function(assembly):
    """The listing split at its function labels, each body as a list of stripped instruction lines.

    Directives (`.text`, `.align`, `.globl`, …) and labels are dropped: what this file is about is
    which instructions are emitted and in what order, and a `.size` line between them is noise.
    """
    bodies, current = {}, None
    for line in assembly.splitlines():
        label = re.match(r"^(\w+):", line)
        if label:
            current = bodies.setdefault(label.group(1), [])
            continue
        text = line.strip()
        if current is not None and text and not text.startswith((".", "|", "#")):
            current.append(text)
    return bodies


def _pair_at(body, first, second):
    """True when `first` is immediately followed by `second` somewhere in `body`."""
    return any(re.search(first, body[i]) and re.search(second, body[i + 1])
               for i in range(len(body) - 1))


def test_the_unmask_saves_the_sr_and_then_clears_the_mask(emitted):
    """THE CASE THIS FILE EXISTS FOR — `Vsync`'s door, whose cycles no Tier 3 row counts.

    The order is the claim, not the presence: a save AFTER the `andi` reads back an SR whose mask
    this instruction has already cleared, so `os_ipl_restore` would hand the caller IPL 0 instead of
    the level it was called at, and every caller of a routine that waits would come back unmasked.
    """
    body = emitted["probe_unmask"]
    assert _pair_at(body, SAVE, UNMASK_MASK), (
        f"os_ipl_unmask did not emit `move.w %sr,<d>` followed by `andi.w #0xf8ff,%sr`: {body}")


def test_the_raise_saves_the_sr_and_then_sets_the_mask(emitted):
    """...and the other direction, which is the pair the ROM's own `Giaccess` opens with. Pinned in
    the same file because the two halves are one door and a change to either is the same edit."""
    body = emitted["probe_raise"]
    assert _pair_at(body, SAVE, RAISE_MASK), (
        f"os_ipl_raise did not emit `move.w %sr,<d>` followed by `ori.w #0x700,%sr`: {body}")


def test_the_restore_writes_the_whole_sr_back(emitted):
    """`move.w <d>,sr` — the register and not the three mask bits, which is what the kit's typedef
    says: a target half that put back only the field would silently drop the caller's condition
    codes."""
    body = emitted["probe_restore"]
    assert any(re.search(RESTORE, line) for line in body), (
        f"os_ipl_restore did not emit `move.w <d>,%sr`: {body}")


def test_a_project_target_half_was_found():
    """The control. Every case above is parametrized over the projects that HAVE a target half, so a
    glob that stopped matching would leave this file passing with nothing compiled."""
    assert TARGET_HALVES, (
        f"no project under {PROJECTS} ships an {TARGET_HALF} — this suite tested nothing")
