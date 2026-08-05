"""Differential test harness: real 68000 code (oracle) vs the reconstruction (candidate).

Both run on the same flat memory image; a green case means byte-for-byte identical
final memory. The candidate is the project's compiled ``.so`` (``lib`` in project.toml),
driven through ctypes.
"""
import ctypes
import re

from . import os_map
from . import project

_CFG = project.current()                 # bound by project.load(); it also put oracle/ on sys.path

import loader  # noqa: E402  (module access: load_image() sets loader.PROGRAM_END, read below)
from loader import load_image, IMAGE_SIZE  # noqa: E402
import emu  # noqa: E402

PRG = _CFG.prg                                        # e.g. projects/buggyboy/bin/BUGGYBOY.PRG
NAMES = _CFG.names
LIB = _CFG.lib

BASE_IMAGE = load_image(PRG)             # loaded + relocated once; tests copy & poke it
_lib = ctypes.CDLL(str(LIB))

# The Dosound side-effect ledger (see differential()) is an OPTIONAL part of a candidate's ABI: a
# game that never issues XBIOS Dosound has nothing to log. ctypes resolves a symbol on first
# attribute access, so probe the three once here — otherwise a candidate lacking them would fail at
# *import* with a bare dlsym AttributeError rather than being served without the ledger.
_DOSOUND_LEDGER_ABI = ("g_dosound_log_reset", "g_dosound_log_count", "g_dosound_log_args")
_has_dosound_ledger = all(hasattr(_lib, sym) for sym in _DOSOUND_LEDGER_ABI)
if _has_dosound_ledger:
    _lib.g_dosound_log_count.restype = ctypes.c_uint32
    _lib.g_dosound_log_args.restype = ctypes.POINTER(ctypes.c_uint32)

# The refused-os_*-call tally (see _vet_no_os_refusal) is REQUIRED ABI, unlike the ledger above.
# The Dosound ledger can be served without: the oracle's own Dosound stream says when it was needed,
# so its absence fails loudly at the moment it matters. The refusal tally has no such witness — the
# oracle's count is zero by construction — so a missing symbol would silently reopen the false-green
# class the tally exists to close, on a suite that stays entirely green. Refuse to run instead.
_OS_REFUSAL_ABI = ("g_os_refusal_reset", "g_os_refusal_count", "os_refused")
_missing_refusal_abi = [sym for sym in _OS_REFUSAL_ABI if not hasattr(_lib, sym)]
if _missing_refusal_abi:
    raise RuntimeError(
        f"{LIB} exports no {'/'.join(_missing_refusal_abi)} — tools/recreate_kit/src/os_refusal.c "
        f"is not linked into {_CFG.name}'s candidate. Without it a refused os_* call is tallied on "
        f"the oracle side only, and a reconstruction that drops a guard the original has stays "
        f"green (see TRAP_MODEL.md). Build the candidate through kit.mk, whose SRC sweeps "
        f"$(KIT)/src/*.c.")
_lib.g_os_refusal_count.restype = ctypes.c_uint32


def _load_name_map():
    """addr -> name, from names.txt `var`/`fn` lines, for readable diff reports."""
    m = {}
    for line in NAMES.read_text().splitlines():
        mm = re.match(r"\s*(?:var|fn)\s+0x([0-9a-fA-F]+)\s+(\S+)", line)
        if mm:
            m[int(mm.group(1), 16)] = mm.group(2)
    return m


NAME_MAP = _load_name_map()


def label(addr):
    """Nearest named global at or below addr, as 'name+off' (or bare hex)."""
    best = max((a for a in NAME_MAP if a <= addr), default=None)
    if best is None or addr - best > 0x40:
        return f"0x{addr:x}"
    off = addr - best
    return NAME_MAP[best] + (f"+{off}" if off else "")


# ---- the TOS model's fixed memory map (mirror of include/os.h) ----
# These addresses are KIT-WIDE (one set of C constants serves every game), while load_base /
# image_size are per-project. tools/recreate_kit/test/test_os_memory_map.py pins this mirror equal
# to os.h; _vet_os_memory_map() below checks the addresses actually fit the bound project's image.
# Two pieces of the mirror live elsewhere and are re-exported here, so `harness.*` still reads as one
# map: OS_HEAP_BASE in oracle/emu.py (its per-run Malloc guard needs it) and the poked-input block in
# os_map.py (harness.py and emu.py both guard it, and neither can import the other).
OS_IMAGE_SIZE = 0x100000     # image length the C model bounds its copies against (vetted below)
OS_HEAP_BASE = emu.OS_HEAP_BASE   # modeled Malloc bump-allocates upward from here
OS_FS_TABLE = 0xBF000        # staged-file table base
OS_FS_STAGING = 0xC0000      # raw file bytes grow upward from here
OS_FS_ENTRY = 36             # name[16] | staging u32 | size u32 | cursor u32 | open u32 | cap u32
OS_FS_SLOTS = 8              # entries in the table; staging a ninth file would overrun it
OS_FS_NAME = 16
# Field offsets within one entry. stage_files() writes each field by name rather than concatenating
# them in order, so that reordering a field in os.h fails test_os_memory_map.py's pin loudly
# instead of drifting silently — which is exactly how the capacity field was first missed.
OS_FS_OFF_STAGING = 16       # u32: where this file's bytes live in the staging area
OS_FS_OFF_SIZE = 20          # u32: current length in bytes
OS_FS_OFF_CURSOR = 24        # u32: read/write position
OS_FS_OFF_OPEN = 28          # u32: nonzero while a handle is open on this slot
OS_FS_OFF_CAPACITY = 32      # u32: staging bytes reserved; os_fwrite refuses to exceed it
OS_FS_FIRST_HANDLE = 6
OS_DOSOUND_LOG_MAX = 256     # ledger cap, on BOTH sides (shim.c's mirror and src/dosound_log.c)

OS_SUPER_TOKEN = 0x00535550  # the cookie GEMDOS Super(0) returns; Super(cookie) restores

# The harness-poked model state (os.h, 0x600..0x61f). Re-exported rather than defined here: both
# this module and oracle/emu.py guard the block, and emu cannot import harness (harness imports it),
# so recreate_kit/os_map.py is its one home — which also keeps it importable with nothing built, for
# the kit's own suite. `harness.OS_CON_PENDING` and friends keep working through these names.
OS_CON_PENDING = os_map.OS_CON_PENDING
OS_CON_CHAR = os_map.OS_CON_CHAR
OS_RANDOM_VALUE = os_map.OS_RANDOM_VALUE
OS_PSG_REGS = os_map.OS_PSG_REGS
OS_PSG_NREGS = os_map.OS_PSG_NREGS
OS_PSG_WRITE = os_map.OS_PSG_WRITE
OS_POKE_BLOCK_END = os_map.OS_POKE_BLOCK_END


# Does the modeled Malloc heap sit inside this project's own program? If so, any block the model
# hands out lands ON TOP of the program's code/data. _vet_os_memory_map() refuses that outright
# unless project.toml waives it, and emu.run() re-checks the waiver's claim on every run
# (emu._vet_no_malloc_over_program) — the waiver asserts something about the game, not about the kit.
_HEAP_OVER_PROGRAM = emu.heap_overlaps_program()

# The poked-input block's overlap is NOT cached the way the heap's is above: the three guards below
# key on it, and _vet_os_memory_map() is re-runnable — projects/joust/recreate/test/test_os_traps.py
# pins the import-time check by monkeypatching loader.LOAD_BASE and calling it again, which a value
# frozen at import would silently ignore. It is emu.poked_input_overlaps_program(), read live, and
# on make_image's hot path the cheap range test short-circuits ahead of it.


def _overlap_error(name, addr, waiver=""):
    """The shared diagnostic for a TOS-model region that collides with the loaded program."""
    return RuntimeError(
        f"{name} ({addr:#x}, tools/recreate_kit/include/os.h) lies inside {_CFG.name}'s "
        f"program, which ends at {loader.PROGRAM_END:#x} — a Malloc block or a staged file "
        f"would overwrite its own code/bss. Move that region (and its Python mirror, in harness.py, "
        f"os_map.py or oracle/emu.py) above the program, or lower load_base in "
        f"{_CFG.dir / project.CONFIG_NAME}." + waiver)


def _vet_os_memory_map():
    """Refuse to run if OS_HEAP_BASE / OS_FS_TABLE / OS_FS_STAGING / the poked-input block, or
    OS_IMAGE_SIZE, don't fit this project's image.

    NOT every kit-wide region: os.h also fixes OS_KBDVBASE (0x500, the KBDVBASE struct XBIOS
    Kbdvbase returns) and OS_SCREEN_BASE (0x8000, what Physbase/Logbase return), and neither is
    checked here or anywhere else. Both used to be covered incidentally by the `load_base >= 0x620`
    floor below — every project loaded at 0x10000, so both regions were necessarily below every
    program — and the poked-input waiver removes exactly that coverage: at projects/wonderboy's
    load_base of 0x3f8, 0x500 and 0x8000 are both inside a live program. The Kbdvbase READER is
    caught per run by emu._vet_no_poked_input_read, but only while the poked block ALSO overlaps
    (that guard's predicate is about the block, not about 0x500); Physbase/Logbase are caught by
    nothing at all. See TRAP_MODEL.md, "Two regions this leaves unvetted".

    A program that reaches OS_HEAP_BASE or OS_FS_TABLE would have its own code/bss silently
    overwritten by a Malloc block or a staged file — nothing else would catch that, since both are
    plain image writes. Staging at or above the stack guard is the mirror hazard: those bytes are
    dropped from the diff. (A too-small image_size is already caught loudly by stage_files.)

    The heap check has one opt-out: only a GEMDOS Malloc ever writes at OS_HEAP_BASE, so a game
    that issues none can declare ``tos_malloc_unused = true`` in its project.toml (which must
    justify it) and let its program cover that region. OS_FS_TABLE has no such waiver — the
    harness stages files itself, so an overlap there is always live.
    """
    if _HEAP_OVER_PROGRAM and not _CFG.tos_malloc_unused:
        raise _overlap_error(
            "OS_HEAP_BASE", OS_HEAP_BASE,
            " If this game issues no GEMDOS Malloc at all, `tos_malloc_unused = true` in "
            "project.toml waives this check (emu.run() then enforces that claim per run).")
    if OS_FS_TABLE < loader.PROGRAM_END:
        raise _overlap_error("OS_FS_TABLE", OS_FS_TABLE)
    if OS_FS_STAGING >= emu.STACK_GUARD_LO:
        raise RuntimeError(
            f"OS_FS_STAGING ({OS_FS_STAGING:#x}, tools/recreate_kit/include/os.h) is at or above "
            f"the stack guard {emu.STACK_GUARD_LO:#x} — staged file bytes would land in the band "
            f"the differential drops. Raise image_size in {_CFG.dir / project.CONFIG_NAME}, or "
            f"move the region down.")
    if emu.poked_input_overlaps_program() and not _CFG.tos_poked_input_unused:
        raise RuntimeError(
            f"the harness-poked input block ({OS_CON_PENDING:#x}..{OS_POKE_BLOCK_END - 1:#x}, "
            f"tools/recreate_kit/include/os.h) is not below {_CFG.name}'s program, which loads at "
            f"{loader.LOAD_BASE:#x} — a staged keystroke, Random value or PSG register would be "
            f"poked ON TOP of its own code with no diagnostic. Move that block (and its Python "
            f"mirror, recreate_kit/os_map.py) down, or raise load_base in "
            f"{_CFG.dir / project.CONFIG_NAME}. If the game reads NONE of that state — no "
            f"Bconstat/Bconin/Crawio, no Random, no Giaccess, no Kbdvbase — "
            f"`tos_poked_input_unused = true` in project.toml (which must justify it) waives this "
            f"check. Two guards then enforce the claim instead of trusting it: make_image() refuses "
            f"any poke landing in the block, and emu.run() refuses any run in which the GAME's own "
            f"code reads it.")
    if OS_IMAGE_SIZE != loader.IMAGE_SIZE:
        raise RuntimeError(
            f"OS_IMAGE_SIZE ({OS_IMAGE_SIZE:#x}, tools/recreate_kit/include/os.h) is not "
            f"{_CFG.name}'s image_size ({loader.IMAGE_SIZE:#x}) — os_fread/os_fwrite bound their "
            f"copies against the C constant, so they would refuse a legitimate transfer above it "
            f"(or, were it larger, copy past the end of the buffer). Keep the two equal: change "
            f"image_size in {_CFG.dir / project.CONFIG_NAME}, or OS_IMAGE_SIZE and its Python "
            f"mirror above.")


_vet_os_memory_map()


def _poked_input_waiver_error(subject):
    """The shared diagnostic for staging poked input into a block that lies inside the program."""
    return RuntimeError(
        f"{_CFG.name} staged {subject}, but the harness-poked input block "
        f"({OS_CON_PENDING:#x}..{OS_POKE_BLOCK_END - 1:#x}) lies INSIDE its program, which loads at "
        f"{loader.LOAD_BASE:#x} and ends at {loader.PROGRAM_END:#x} — writing the poke would land "
        f"on the game's own code, on both sides, and the diff would compare two identically "
        f"corrupted runs. That layout is only permitted because its {project.CONFIG_NAME} declares "
        f"`tos_poked_input_unused = true`, the claim that the game reads NONE of this state. Either "
        f"the claim is wrong — drop the flag and move the block (include/os.h + its mirror, "
        f"recreate_kit/os_map.py) above the program, or raise load_base — or this case does not "
        f"need the poke. (Those addresses being the game's own code is exactly why this is refused: "
        f"nothing here can tell a poke staging kit model state from one deliberately patching the "
        f"program at the same place, so both are refused rather than one silently served.)")


def _vet_poked_input_available(what):
    """Refuse to BUILD a poked-input poke for a project whose program covers the block.

    Keyed on the overlap, never on the ``tos_poked_input_unused`` flag: a project that sets the flag
    while loading clear of the block (load_base >= OS_POKE_BLOCK_END) has nothing to collide with and
    keeps console_key()/psg_regs(), and a project that loses the overlap later stops being refused
    without anyone editing the flag. When the overlap IS present and the flag is not set,
    _vet_os_memory_map() already refused to bind the project, so the flag adds nothing to test.

    This is the friendly early error, not the guard: it names *what* was staged, at the line that
    staged it, before an image exists. The guard that cannot be bypassed is in make_image(), which
    sees every poke however it was built; the guard over the GAME's own reads of the block is
    emu._vet_no_poked_input_read().
    """
    if emu.poked_input_overlaps_program():
        raise _poked_input_waiver_error(what)


def _vet_no_poke_into_poked_input(addr, length):
    """Refuse one poke of ``length`` bytes at ``addr`` if it lands in the poked-input block while
    that block lies inside the program. Called from make_image() for every poke.

    The range test is two comparisons on an address that is almost always far above the block, and
    it short-circuits, so for every project the hazard cannot reach this costs one call per poke on
    make_image's hot path and never reaches the overlap question at all.

    LIMIT: under the overlap those addresses ARE the game's code, and nothing here can tell a poke
    that stages kit model state from one that deliberately patches the program's own bytes at the
    same place (which test_bootstrap.py does elsewhere in the image). It refuses both. Over-strict
    fails loudly, which is the right way round for this contract; the diagnostic says so.
    """
    if os_map.poke_hits_poked_input(addr, length) and emu.poked_input_overlaps_program():
        raise _poked_input_waiver_error(f"a {length}-byte poke at {addr:#x}")


def console_key(char, scancode=0):
    """Pokes staging ONE pending console keystroke, for Bconstat / Bconin / Crawio.

    ``char`` is the ASCII character the program reads; ``scancode`` its IKBD scancode, which sits in
    the high word the way TOS returns it. Bconin consumes the key, so one call is one keypress.
    The pending flag and the character are built together because a test that set only one would
    leave the console half-armed — armed with a NUL, or holding a character nothing reports.
    """
    _vet_poked_input_available("a console keystroke")
    return {OS_CON_PENDING: (1).to_bytes(4, "big"),      # nonzero = a character is waiting
            OS_CON_CHAR: ((scancode << 16) | ord(char)).to_bytes(4, "big")}


def psg_regs(values):
    """Pokes staging the YM2149 register file XBIOS Giaccess reads (os.h OS_PSG_REGS).

    ``values`` = {register: byte}. Every register not listed reads 0 — the value a fresh image
    already has, since the model asserts nothing about the chip's power-on contents. The whole file
    is one poke, so a partially written file is not expressible.
    """
    _vet_poked_input_available("the YM2149 register file")
    regfile = bytearray(OS_PSG_NREGS)
    for reg, value in values.items():
        assert 0 <= reg < OS_PSG_NREGS, f"YM2149 register {reg} is outside 0..{OS_PSG_NREGS - 1}"
        regfile[reg] = value
    return {OS_PSG_REGS: bytes(regfile)}


def stage_files(files):
    """Lay staged files into FS-table + staging pokes so os_fopen/os_fread can serve them.

    ``files`` = [(name, data), ...] or [(name, data, capacity), ...] in slot order; ``capacity`` is
    the staging space RESERVED for the file — what os_fwrite may grow it to — and defaults to the
    data's own length, which is all a read-only file needs. Returns (pokes, handles), where
    handles[name] is the handle os_fopen(name) will return. Merge ``pokes`` into a test's poke
    dict. If these constants drift from os.h the open/read test fails (the cross-language pin),
    since os_fopen would look at the wrong table address.
    """
    assert len(files) <= OS_FS_SLOTS, (
        f"{len(files)} files staged into a {OS_FS_SLOTS}-slot table — the extra entries would be "
        f"written past its end, over the staging area os_fread then serves bytes from")
    pokes, handles, off = {}, {}, OS_FS_STAGING
    for slot, spec in enumerate(files):
        name, data = spec[0], spec[1]
        capacity = spec[2] if len(spec) > 2 else len(data)
        nb = name.encode("ascii")
        assert len(nb) < OS_FS_NAME, f"{name!r} too long for the {OS_FS_NAME}-byte name field"
        assert capacity >= len(data), (
            f"{name!r}: capacity {capacity} is less than its own {len(data)} staged bytes")
        entry = bytearray(OS_FS_ENTRY)
        entry[:len(nb)] = nb                           # the rest of the name field stays NUL
        for field, value in ((OS_FS_OFF_STAGING, off), (OS_FS_OFF_SIZE, len(data)),
                             (OS_FS_OFF_CURSOR, 0), (OS_FS_OFF_OPEN, 0),
                             (OS_FS_OFF_CAPACITY, capacity)):
            entry[field:field + 4] = value.to_bytes(4, "big")
        pokes[OS_FS_TABLE + slot * OS_FS_ENTRY] = bytes(entry)
        pokes[off] = bytes(data)
        handles[name] = OS_FS_FIRST_HANDLE + slot
        off += capacity                    # step by the RESERVATION: two files must not overlap
        assert off <= emu.STACK_GUARD_LO, "staged files overflowed the stack guard"
    return pokes, handles


def make_image(pokes=None):
    """Fresh copy of the loaded image with {addr: bytes} written in.

    Every poke passes _vet_no_poke_into_poked_input() — the one layer no caller can go round, since
    a poke that is never applied changes nothing. The two builders above check earlier and more
    kindly, but they are not the whole surface: the block holds three kinds of state and the kit
    ships two builders, so hand-writing {OS_RANDOM_VALUE: ...} into a poke dict is the ONLY way to
    stage an XBIOS Random, and that idiom is in use (projects/joust/recreate/test/test_os_traps.py).
    """
    img = bytearray(BASE_IMAGE)
    for addr, data in (pokes or {}).items():
        _vet_no_poke_into_poked_input(addr, len(data))
        img[addr:addr + len(data)] = data
    return img


def hi_garbage(rng, low_word):
    """A 32-bit value with low_word in the low 16 bits and random garbage in the high 16. For a
    register the code uses only as a word (.w ops: dbf / lsl.w / adda.w), feeding this proves the
    high bits are ignored — the reconstruction's (u)int16 casts must drop them as the 68k does.
    """
    return (rng.randint(0, 0xffff) << 16) | (low_word & 0xffff)


def _vet_exclude_bands(exclude, min_a7):
    """Guard every diff `exclude` band before it silently drops bytes from the comparison.

    An exclude band suspends the byte-for-byte guarantee for its range, so it must be provably
    stack scratch — not program output. Two cheap checks against the deepest stack pointer the
    oracle reached (min_a7 — stack grows down, so live stack is [min_a7, base)):
      (A) the band must extend past min_a7 — a band lying entirely below where A7 ever descended
          cannot be stack, so excluding it could hide real writes;
      (D) it must cover no *named* global (names.txt var/fn) that sits below min_a7 — such a global
          is provably not stack, so dropping it from the diff could mask a divergence. A named
          global at/above min_a7 is fine: it is legitimately reused as scratch while the stack
          sits over it (e.g. _start relocates its stack across trace_pc).
    A conservatively-wide band (untouched bytes below the used stack, none of them named) passes.
    """
    for lo, hi in (exclude or ()):
        assert hi > min_a7, (
            f"exclude band [{lo:#x},{hi:#x}) lies entirely below the deepest stack pointer "
            f"{min_a7:#x}; those bytes were never stack, so excluding them could hide real output")
        named_below = sorted(a for a in NAME_MAP if lo <= a < min(hi, min_a7))
        assert not named_below, (
            f"exclude band [{lo:#x},{hi:#x}) covers named global(s) below the stack: "
            + ", ".join(f"{NAME_MAP[a]}@{a:#x}" for a in named_below)
            + " — refusing to drop a known global from the diff")


def _vet_no_os_refusal(entry):
    """Reject a run in which the CANDIDATE made an os_* call the TOS model refuses — a FALSE GREEN.

    Call it after EVERY candidate run, the poison pass included — a refusal reached only on the
    poisoned image is the same untested-but-green case.

    The oracle's own tally is necessarily zero here: a refused trap sets ``g_unmodeled`` and
    ``emu.run()`` raises long before the diff. So any candidate-side refusal is an asymmetry, and it
    is the one that hides a missing guard (include/os.h, "refusing a call, on BOTH sides").
    """
    refusals = _lib.g_os_refusal_count()
    if not refusals:
        return
    raise AssertionError(
        f"function @ {entry:#x}: the candidate made {refusals} os_* call(s) the TOS model REFUSES "
        f"to serve, while the oracle made none — so a clean diff here would prove nothing. A refusal "
        f"rejects the ORACLE's whole run (g_unmodeled), but on the candidate side it only returns a "
        f"sentinel and touches neither the out-param nor the image, so the candidate is free to "
        f"differ exactly where the oracle declines to look. Three causes: the candidate is missing a "
        f"guard the original has (the Bconstat gate before Bconin, a test of Fopen's handle); or "
        f"this case needs the state staged (harness.console_key(), harness.stage_files()) so BOTH "
        f"sides execute the call; or a stop_pc checkpoint ended the oracle before a call the "
        f"candidate still makes. See tools/recreate_kit/TRAP_MODEL.md.")


def _attribution_check(img, entry, regs, glue, o_final, o_writes, guard_lo, excluded,
                       stop_pc, max_insns):
    """Guard against a *coincidental* pass: the candidate may match the oracle's final image while
    never actually writing some byte the oracle wrote — because that byte already held the oracle's
    value (an output landing in a zeroed/base region). Re-run both cores on a copy of the input in
    which every oracle-written byte is poisoned with a canary (its normal final value, inverted). A
    byte the candidate fails to write now stays canary instead of matching, so the omission shows.
    Only meaningful once the normal pass is clean; opt-in (poison=True) since poisoning an output
    that also steers control flow could perturb a complex function's run."""
    poisoned = bytearray(img)
    for a in o_writes:
        if a < guard_lo:                     # only the diffed region matters; stack canaries are moot
            poisoned[a] = o_final[a] ^ 0xff
    po_final, _, _ = emu.run(poisoned, entry, regs, stop_pc=stop_pc, max_insns=max_insns)
    buf = (ctypes.c_uint8 * IMAGE_SIZE).from_buffer(bytearray(poisoned))
    # This is a SECOND candidate run, so it needs the same per-run bookkeeping the first one got:
    # poisoning inverts oracle-written bytes, which can steer the candidate down a path the plain
    # run never took — including into a refused os_* call. Reset before, vet after, or that refusal
    # is tallied into a count nobody reads and the pass reports a clean attribution.
    _lib.g_os_refusal_reset()
    glue(_lib, buf)
    _vet_no_os_refusal(entry)
    pc_final = bytes(buf)
    bad = [a for a in range(guard_lo) if po_final[a] != pc_final[a] and not excluded(a)]
    if bad:
        a = bad[0]
        raise AssertionError(
            f"attribution (poison) check: candidate diverges on a poisoned-output image at "
            f"{label(a)} @ 0x{a:x} (oracle={po_final[a]:#04x} cand={pc_final[a]:#04x}, {len(bad)} "
            f"bytes) — it likely never wrote a byte the oracle wrote, passing the plain diff by "
            f"coincidence")


def differential(entry, regs, glue, stop_pc=0, exclude=None, max_insns=200_000, poison=False):
    """Run oracle + candidate on the same image. Return (diffs, info).

    ``diffs`` is the list of (addr, oracle, cand) byte differences (stack-guard excluded).
    ``info`` carries {"writes", "regs", "ret"}: the oracle write-set, the oracle's registers at
    return (``emu.REPORTED_REGS`` — d0..d7 and a0..a6 — plus its ledger entries), and whatever the
    candidate glue returned (its D0, or None for void glues).
    ``regs`` are the oracle's input registers; ``glue(lib, buf)`` runs the candidate on a
    mutable ctypes copy of the same image with the matching arguments.

    ``stop_pc`` diffs at a checkpoint PC instead of at rts (for a function that never returns;
    see emu.run). ``exclude`` is an optional list of (lo, hi) byte bands to drop from the diff
    in addition to the default stack guard — used when the function relocates its own stack
    outside [STACK_GUARD_LO, IMAGE_SIZE) (e.g. _start moves A7 to 0x1b044). The candidate is
    pure C and never writes a machine stack, so excluding the oracle's stack band is sound.
    ``max_insns`` caps the oracle run (raise it for data-heavy functions like the unpacker).
    Raises before comparing anything if the candidate made an ``os_*`` call the TOS model refuses
    (``_vet_no_os_refusal``) — such a case tests nothing, however clean its bytes look.
    ``poison`` runs an extra attribution pass (``_attribution_check``): re-run both cores on an
    image whose oracle-written bytes are pre-poisoned, catching a candidate that matches by
    coincidence without actually writing a byte the oracle wrote. Opt-in (safe for leaf functions).
    """
    img = make_image(regs.pop("_pokes", None))
    o_final, o_writes, o_regs = emu.run(img, entry, regs, stop_pc=stop_pc, max_insns=max_insns)

    _vet_exclude_bands(exclude, o_regs["min_a7"])

    Buf = ctypes.c_uint8 * IMAGE_SIZE
    buf = Buf.from_buffer(bytearray(img))
    if _has_dosound_ledger:
        _lib.g_dosound_log_reset()       # fresh Dosound ledger for this candidate run (see below)
    _lib.g_os_refusal_reset()            # ...and a fresh refused-os_*-call tally (see below)
    cand_ret = glue(_lib, buf)
    c_final = bytes(buf)

    # Before anything is compared: a candidate that made a refused os_* call has not been tested by
    # this case at all, however clean the bytes look. See _vet_no_os_refusal.
    _vet_no_os_refusal(entry)

    def excluded(a):
        return any(lo <= a < hi for lo, hi in (exclude or ()))

    # Diff only [0, STACK_GUARD_LO): the oracle uses the guard region above as a real machine
    # stack (return address, saved registers) that the C reconstruction has no analogue for.
    # Fast path — compare that prefix at C speed; only walk it byte-by-byte when it actually
    # differs (a failure, or an excluded band like _start's relocated stack). This keeps the
    # scan cheap as IMAGE_SIZE grows (the prefix is ~1 MiB now).
    guard_lo = emu.STACK_GUARD_LO
    if bytes(o_final[:guard_lo]) == bytes(c_final[:guard_lo]):
        diffs = []
    else:
        diffs = [(a, o_final[a], c_final[a])
                 for a in range(guard_lo)
                 if o_final[a] != c_final[a] and not excluded(a)]

    # Write-set completeness: the guard cutoff above is only sound if the oracle used that
    # region purely as stack. A write in [STACK_GUARD_LO, STACK_TOP - STACK_SCRATCH) is program
    # output the diff would silently hide — fail loudly so it can't pass as verified.
    stray = sorted(a for a in o_writes
                   if emu.STACK_GUARD_LO <= a < emu.STACK_TOP - emu.STACK_SCRATCH)
    if stray:
        raise AssertionError(
            f"oracle wrote {len(stray)} byte(s) in the reserved stack-guard band "
            f"(e.g. {label(stray[0])} @ 0x{stray[0]:x}) — real output masked by the guard cutoff")

    # Side-effect ledger: XBIOS Dosound(A0) writes the YM2149, not RAM, so a wrong/missing command
    # list is invisible to the image diff. Compare the oracle's ordered Dosound trap stream against
    # the candidate's g_dosound ledger — both list pointers are Ghidra image addresses — so an
    # off-image sound trigger with the wrong list fails here even though it touches no memory.
    # The ledger is optional ABI (see _has_dosound_ledger); a candidate without one is only served
    # while the oracle issues no Dosound at all, so the check is never silently lost.
    o_dosound = o_regs.get("dosound", [])
    if _has_dosound_ledger:
        n = _lib.g_dosound_log_count()
        c_args = _lib.g_dosound_log_args()
        c_dosound = [c_args[i] for i in range(n)]
        # Both ledgers stop logging SILENTLY at OS_DOSOUND_LOG_MAX, so two streams that diverge
        # only past the cap truncate to the same list and compare equal. Fail loudly instead.
        assert len(o_dosound) < OS_DOSOUND_LOG_MAX and len(c_dosound) < OS_DOSOUND_LOG_MAX, (
            f"Dosound ledger hit its cap ({OS_DOSOUND_LOG_MAX}): oracle={len(o_dosound)} "
            f"cand={len(c_dosound)} — the compare beyond it would be blind; shorten the run or "
            f"raise OS_DOSOUND_LOG_MAX in include/os.h (its mirror in harness.py is pinned to it)")
        if o_dosound != c_dosound:
            raise AssertionError(
                f"Dosound ledger mismatch: oracle={[hex(x) for x in o_dosound]} "
                f"cand={[hex(x) for x in c_dosound]} — off-image XBIOS Dosound(A0) diverged")
    elif o_dosound:
        raise AssertionError(
            f"the oracle issued {len(o_dosound)} XBIOS Dosound(A0) call(s) but {_CFG.name}'s "
            f"candidate exports no Dosound ledger ({'/'.join(_DOSOUND_LEDGER_ABI)}) — the command "
            f"lists cannot be compared, so a divergence here would pass unnoticed")

    if poison and not diffs:
        _attribution_check(img, entry, regs, glue, o_final, o_writes, guard_lo, excluded,
                           stop_pc, max_insns)

    return diffs, {"writes": o_writes, "regs": o_regs, "ret": cand_ret}


def report(diffs):
    return "\n".join(f"  {label(a)} (0x{a:x}): oracle={o:#04x} cand={c:#04x}" for a, o, c in diffs)