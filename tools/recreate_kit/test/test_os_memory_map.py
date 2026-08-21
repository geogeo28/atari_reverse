"""Cross-language pin: the TOS model's memory map must agree between C and Python.

``tools/recreate_kit/include/os.h`` — compiled into both the oracle shim and every reconstruction's
OS wrappers — is the canonical declaration of the staged-file table layout, the modeled Malloc base
and the harness-poked input block. Its Python mirror is split across three files (``PY_MIRRORS``
below says which holds what and why). CLAUDE.md §5 requires one canonical definition with the other
pinned equal by a test; C and Python cannot import each other, so this parses both sources textually.

Drift here is not loud on its own: os_fopen would simply look at a table address the harness never
wrote and report "file not staged", or Malloc would hand out a block the harness thinks is free.
Both sources are parsed rather than imported because ``harness`` needs a bound project and a built
candidate ``.so``; this test must run in a bare checkout. ``os_map`` is the one Python mirror with no
such dependency, so the last case below can import it and check the *guarded* region against os.h
rather than only the constants' values.
"""
import re
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
OS_H = KIT / "include" / "os.h"
# The Python mirror is split across three files: harness.py holds the file-staging map it pokes into
# the image, oracle/emu.py holds OS_HEAP_BASE (which its per-run Malloc guard needs), and os_map.py
# holds the harness-poked input block (which harness.py and emu.py BOTH guard, so neither can own
# it). Each constant must be defined in exactly one of them (asserted below) so there is still one
# source; harness.py re-exports the other two files' names, and a re-export is not a definition.
PY_MIRRORS = (KIT / "harness.py", KIT / "oracle" / "emu.py", KIT / "os_map.py")

sys.path.insert(0, str(KIT.parent))                   # reverse/tools, so `recreate_kit` imports
from recreate_kit import os_map   # noqa: E402  (importable with nothing built, unlike harness/emu)

# Every constant that exists on both sides. os.h is the canonical definition.
PINNED = ("OS_IMAGE_SIZE", "OS_HEAP_BASE", "OS_FS_TABLE", "OS_FS_STAGING", "OS_FS_ENTRY",
          "OS_FS_SLOTS", "OS_FS_NAME", "OS_FS_FIRST_HANDLE", "OS_DOSOUND_LOG_MAX",
          # the two off-image ledger caps: both sides truncate at the SAME entry, or two streams
          # that diverge past the cap would compare equal (harness.differential asserts below them)
          "OS_PSG_LOG_MAX",
          # ...and the seeded-hardware read ledger's (Phase 7), for the same reason. The modeled
          # ADDRESSES need no entry here: emu.py reads them from the .so (osh_hw_addr_table), so
          # there is no second copy in Python that could drift from os.h's table.
          "OS_HW_LOG_MAX",
          # ...and that ledger's event kinds. The C tags each entry and the Python compares them, so
          # a value changed on one side alone would make every read compare as a write, silently.
          "OS_PSG_EVENT_WRITE", "OS_PSG_EVENT_READ",
          # the staged-file entry's field offsets: harness.stage_files writes each field by name,
          # so a field REORDERED in os.h drifts silently unless both sides are pinned too
          "OS_FS_OFF_STAGING", "OS_FS_OFF_SIZE", "OS_FS_OFF_CURSOR", "OS_FS_OFF_OPEN",
          "OS_FS_OFF_CAPACITY",
          # the harness-poked model state (TRAP_MODEL.md): both cores must read the same bytes
          "OS_CON_PENDING", "OS_CON_CHAR", "OS_RANDOM_VALUE", "OS_PSG_REGS", "OS_PSG_NREGS",
          "OS_PSG_WRITE", "OS_SUPER_TOKEN",
          # ...and the scheduled-write model's two trigger kinds (Phase 8). The sizes need no entry —
          # emu.py reads OS_SCHED_MAX/OS_SCHED_FIELDS from the .so — but these two are an ENCODING
          # the cases are written against, and a value changed on one side alone would turn every
          # `pc` trigger into an `insn` one, which fires at an instruction index instead.
          "OS_SCHED_AT_PC", "OS_SCHED_AT_INSN")


def _c_defines(source, names=None):
    """{name: value} for `#define <name> <int literal>` (an optional u/U suffix).

    With ``names``, only those are looked up. Without, EVERY ``OS_*`` integer define is returned —
    which is what lets the last case below notice a constant nobody remembered to classify.
    """
    if names is None:
        return {name: int(value, 0) for name, value in
                re.findall(r"^#define\s+(OS_\w+)\s+(0x[0-9a-fA-F]+|\d+)[uU]?\b", source, re.M)}
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


def test_every_low_model_address_is_guarded_or_declared_unvetted():
    """Every low-memory region os.h fixes is either inside the guarded poked-input block, or on the
    short list of regions this workspace knows are unvetted.

    A region below LOW_REGION_END can land inside a program that loads at a low base — which
    projects/wonderboy does, at 0x3f8, because its game runs at the absolute address 0x400. The block
    at [OS_CON_PENDING, OS_POKE_BLOCK_END) is guarded from both sides (harness.make_image refuses a
    poke into it; emu.run refuses a run whose traps read it). The two below are not, and are recorded
    as such in TRAP_MODEL.md — so this case exists to make a THIRD one impossible to add quietly:
    a new `#define OS_JOYSTICK_STATE 0x630u` fails here until someone classifies it.

    The scan cannot tell an address from a size or a selector, so it takes every `OS_*` integer in
    [VECTOR_PAGE_END, LOW_REGION_END) — above the 68000 vector page, which no model region may sit
    in, and below the workspace's default load_base, above which no program is low. Most other
    constants in os.h are small sizes, offsets or selectors well under 0x400; the few LARGE ones that
    are not addresses at all are named in NOT_ADDRESSES, which is the classification this case
    demands rather than an escape from it — over-strict fails loudly, which is the right way round.
    """
    VECTOR_PAGE_END = 0x400         # below this is the 68000's exception vector table
    LOW_REGION_END = 0x10000        # the workspace's default load_base: above it, no program is low
    NOT_ADDRESSES = {
        # 4096 entries — the direct-PSG ledger's cap on both sides, not a place in the image. It is
        # this large because that ledger is also the audio-capture mode's data feed (a whole VBL
        # tick's register stream), which is what puts it in this range at all.
        "OS_PSG_LOG_MAX",
        # 4096 entries — the seeded-hardware read ledger's cap on both sides. Sized like the PSG's
        # because these addresses are POLLED (an FDC wait loop reads $fffa01 once per iteration), so
        # a modest cap would truncate an ordinary run. Not a place in the image either.
        "OS_HW_LOG_MAX",
        # 4096 POLLS — the candidate's runaway guard on one busy-wait (src/sched.c's sched_wait8),
        # not a place in the image. It is a count of iterations, and it is this large so that only a
        # wait which was never going to end can reach it; the oracle's own instruction cap bites
        # first for anything a case realistically declares.
        "OS_SCHED_POLL_MAX",
    }
    UNVETTED = {
        # 0x500, the KBDVBASE struct XBIOS Kbdvbase returns. Its only reader is that trap, which IS
        # tallied by osh_poked_input_calls — but the guard keyed on that tally asks about the poked
        # block, not about this address, so a layout covering 0x500 while clearing 0x600 is unseen.
        "OS_KBDVBASE",
        # 0x8000, what Physbase/Logbase return. Tallied by nothing at all: a program handed this and
        # drawing into it scribbles its own code identically on both sides.
        "OS_SCREEN_BASE",
    }
    low = {name: value for name, value in _c_defines(OS_H.read_text()).items()
           if VECTOR_PAGE_END <= value < LOW_REGION_END
           and name not in UNVETTED and name not in NOT_ADDRESSES}
    assert not (NOT_ADDRESSES & UNVETTED), (
        f"{sorted(NOT_ADDRESSES & UNVETTED)} is on both lists — a constant is either an address "
        f"this workspace knows is unvetted or not an address at all, and listing it twice lets a "
        f"real region hide in the wrong one")
    unclassified = {name: value for name, value in low.items()
                    if not os_map.OS_CON_PENDING <= value < os_map.OS_POKE_BLOCK_END}
    assert not unclassified, (
        f"os.h fixes {unclassified} below {LOW_REGION_END:#x}, outside the guarded block "
        f"[{os_map.OS_CON_PENDING:#x}, {os_map.OS_POKE_BLOCK_END:#x}) and off both lists. If it is "
        f"an ADDRESS: bring it inside the block, or add it to UNVETTED and to TRAP_MODEL.md's 'Two "
        f"regions this leaves unvetted'. If it is a large COUNT or SIZE that merely lands in this "
        f"range: add it to NOT_ADDRESSES, with the comment saying why it is not a place in the "
        f"image — filing a size under UNVETTED would register it as a low-memory region.")
    assert low, "no low model addresses parsed at all — the scan is looking at the wrong file"


def test_every_modeled_hardware_address_is_above_the_image():
    """The off-image models are reached only AFTER the image bounds check, so an image that grew
    over their addresses would silently swallow them.

    ``m68k_read_memory_8`` opens with ``if (a < g_size) return g_mem[a];`` and only then decodes the
    PSG ports and the Phase 7 hardware set. Raise ``OS_IMAGE_SIZE`` past ``$ff820a`` and every read
    of the shifter's sync byte becomes an ordinary RAM read: no ledger entry, no ``hw_unseeded``, no
    refusal, no comparison — both models evaporate and every differential goes green, which is
    exactly the silent false green they exist to close.

    Nothing else covers this: the low-address scan above deliberately stops at ``0x10000``, and no
    project has moved ``OS_IMAGE_SIZE`` yet, so the day one does the failure would be a suite that
    got *quieter*. One assertion over both models' addresses, since the exposure is identical.
    """
    c = _c_defines(OS_H.read_text())
    modeled = {name: value for name, value in c.items()
               if name in ("OS_PSG_PORT_SELECT", "OS_PSG_PORT_DATA",
                           "OS_HW_MFP_GPIP", "OS_HW_SHIFTER_SYNC")}
    assert len(modeled) == 4, f"os.h is missing/unparsable for one of the modeled addresses: {modeled}"
    swallowed = {name: value for name, value in modeled.items() if value < c["OS_IMAGE_SIZE"]}
    assert not swallowed, (
        f"OS_IMAGE_SIZE ({c['OS_IMAGE_SIZE']:#x}) covers {swallowed} — those addresses are decoded "
        f"only after shim.c's image bounds check, so an access to one would be served from the "
        f"image and neither model would ever see it")


def test_staged_file_table_fits_below_staging():
    """The table must hold OS_FS_SLOTS entries without running into the staging area below it."""
    c = _c_defines(OS_H.read_text(), PINNED)
    table_bytes = c["OS_FS_SLOTS"] * c["OS_FS_ENTRY"]
    assert c["OS_FS_TABLE"] + table_bytes <= c["OS_FS_STAGING"], (
        f"the {c['OS_FS_SLOTS']}-entry staged-file table at {c['OS_FS_TABLE']:#x} "
        f"({table_bytes} bytes) overruns OS_FS_STAGING at {c['OS_FS_STAGING']:#x}")
