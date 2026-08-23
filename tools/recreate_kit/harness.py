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

# The direct-PSG surfaces (src/psg.c) are optional in the same way and for the same reason: a game
# that never touches $ff8800/$ff8802 has nothing to record, and the ORACLE's own traffic is the
# witness that says when the group was needed — _vet_psg_state raises the moment the oracle uses the
# path against a candidate that cannot answer for it. The MISSING members are kept, not just the
# yes/no: a candidate exporting five of the six is the likely real failure (a half-updated src/psg.c,
# a stale build), and "exports no PSG ledger, here are all six" would send the reader hunting for the
# five that are already there.
_PSG_LEDGER_ABI = ("g_psg_reset", "g_psg_log_count", "g_psg_log_kinds", "g_psg_log_regs",
                   "g_psg_log_vals", "g_psg_file", "g_psg_file_known")
_missing_psg_ledger = [sym for sym in _PSG_LEDGER_ABI if not hasattr(_lib, sym)]
_has_psg_ledger = not _missing_psg_ledger
if _has_psg_ledger:
    _u8p = ctypes.POINTER(ctypes.c_uint8)
    _lib.g_psg_reset.argtypes = [_u8p, ctypes.c_uint32]
    _lib.g_psg_log_count.restype = ctypes.c_uint32
    _lib.g_psg_log_kinds.restype = _u8p
    _lib.g_psg_log_regs.restype = _u8p
    _lib.g_psg_log_vals.restype = _u8p
    _lib.g_psg_file.restype = _u8p
    _lib.g_psg_file_known.restype = ctypes.c_uint32

# The seeded-hardware surfaces (src/hw.c) are optional in exactly the same way and for the same
# reason: a game that branches on no modeled hardware byte has nothing to record, and the ORACLE's
# own read stream is the witness that says when the group was needed — _vet_hw_state raises the
# moment the oracle reads one against a candidate that cannot answer for it.
_HW_LEDGER_ABI = ("g_hw_reset", "g_hw_log_count", "g_hw_log_slots", "g_hw_log_vals", "g_hw_file",
                  "g_hw_file_known")
_missing_hw_ledger = [sym for sym in _HW_LEDGER_ABI if not hasattr(_lib, sym)]
_has_hw_ledger = not _missing_hw_ledger
if _has_hw_ledger:
    _lib.g_hw_reset.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32]
    _lib.g_hw_log_count.restype = ctypes.c_uint32
    _lib.g_hw_log_slots.restype = ctypes.POINTER(ctypes.c_uint8)
    _lib.g_hw_log_vals.restype = ctypes.POINTER(ctypes.c_uint8)
    _lib.g_hw_file.restype = ctypes.POINTER(ctypes.c_uint8)
    _lib.g_hw_file_known.restype = ctypes.c_uint32

# The scheduled-write surfaces (src/sched.c) are optional in exactly the same way and for the same
# reason: a game with no busy-wait to model schedules nothing, and the ORACLE's own schedule is the
# witness that says when the group was needed — differential() raises the moment a case declares one
# against a candidate that cannot answer for it.
_SCHED_ABI = ("g_sched_reset", "g_sched_count", "g_sched_polls", "g_sched_applied",
              "g_sched_refused", "g_sched_exhausted", "g_sched_site_count", "g_sched_site_polls",
              "g_sched_undeclared")
_missing_sched_abi = [sym for sym in _SCHED_ABI if not hasattr(_lib, sym)]
_has_sched = not _missing_sched_abi
if _has_sched:
    _u32p = ctypes.POINTER(ctypes.c_uint32)
    _lib.g_sched_reset.argtypes = [_u32p, ctypes.c_uint32, _u32p, ctypes.c_uint32]
    _lib.g_sched_site_polls.argtypes = [ctypes.c_uint32]
    for _sym in ("g_sched_count", "g_sched_polls", "g_sched_applied", "g_sched_refused",
                 "g_sched_exhausted", "g_sched_site_count", "g_sched_site_polls",
                 "g_sched_undeclared"):
        getattr(_lib, _sym).restype = ctypes.c_uint32

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
OS_PSG_LOG_MAX = 4096        # ...and the direct-PSG ledger's, likewise on both (shim.c, src/psg.c)
OS_HW_LOG_MAX = 4096         # ...and the seeded-hardware read ledger's (shim.c, src/hw.c)

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
# The direct-PSG ledger's event kinds, likewise re-exported from their one home (see os_map).
OS_PSG_EVENT_WRITE = os_map.OS_PSG_EVENT_WRITE
OS_PSG_EVENT_READ = os_map.OS_PSG_EVENT_READ


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


def _poked_input_waiver_error(subject, declarable=False):
    """The shared diagnostic for staging poked input into a block that lies inside the program.

    ``declarable`` adds the ``poked_input_program_data`` remedy, and ONLY the ``make_image`` guard
    passes it. The builder-level guard (`_vet_poked_input_available`) must not: `console_key()` and
    `psg_regs()` stage the MODEL's own state, which no declaration can make seedable, so offering
    the remedy there would send a reader to widen a waiver that buys them nothing and gives up the
    block.
    """
    declaration = ("" if not declarable else
                   f" If the bytes ARE this program's own data — a game variable that happens to "
                   f"share the address — declare the span in {project.CONFIG_NAME}'s "
                   f"`poked_input_program_data`, with the evidence; that permits the seeding and "
                   f"nothing else.")
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
        f"program at the same place, so both are refused rather than one silently served.){declaration}")


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

    THE LIMIT, AND THE ONE WAY ROUND IT. Under the overlap those addresses ARE the game's bytes, and
    nothing here can tell a poke that stages kit model state from one that seeds a game variable
    sharing the address. It refuses both — over-strict fails loudly, which is the right way round —
    UNLESS the project has said which spans are its own program's data, in ``project.toml``'s
    ``poked_input_program_data``. That declaration is the fact the paragraph above says the kit
    cannot have; it permits the SEEDING only, and the real hazard (a trap serving one of those bytes
    back as model state) stays refused per run by ``emu._vet_no_poked_input_read``.
    """
    if not (os_map.poke_hits_poked_input(addr, length) and emu.poked_input_overlaps_program()):
        return
    if os_map.poke_is_declared_program_data(addr, length, _CFG.poked_input_program_data):
        _note_served_over_a_model_field(addr, length)
        return
    raise _poked_input_waiver_error(f"a {length}-byte poke at {addr:#x}", declarable=True)


# Every declared span served this session, as {(addr, length): (field names)} — read by
# test_poked_input_guard.py, and by anyone asking "what did this suite stage over model state?".
# A LEDGER RATHER THAN A WARNING: `warnings` is swallowed by pytest's default filters and a print
# is lost under `-n auto`, so neither would make the mistake loud. This is the lightest mechanism
# that a case can assert on, which is the kit's own convention for every other model surface.
SERVED_OVER_MODEL_FIELDS = {}


def _note_served_over_a_model_field(addr, length):
    """Record a served poke that lands on a field the OS model also names.

    The declaration says those bytes are the GAME's; it cannot say the author meant them that way
    on the day. Wonder Boy's `$604` IS `OS_CON_CHAR` in full, so `make_image({OS_CON_CHAR: ...})` —
    a hand-staged console key, the idiom Joust's suite uses — is now SERVED here instead of refused,
    and would silently become a game-data seed. Recording it is what lets that be noticed: the
    project's own battery asserts the ledger holds exactly the spans it means to stage.
    """
    fields = os_map.poked_input_fields_touched(addr, length)
    if fields:
        SERVED_OVER_MODEL_FIELDS[(addr, length)] = fields


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

    NOT the direct path's seed, though the argument looks identical: this stages the file XBIOS
    ``Giaccess`` reads, which lives IN the image. A routine that reaches the chip through
    ``$ff8800``/``$ff8802`` instead is seeded by ``differential(..., psg_seed=…)`` — one chip, two
    modeled files, and a run that touches both is refused (TRAP_MODEL.md, Phases 3 and 6).
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


def candidate_image(img):
    """The mutable buffer the CANDIDATE runs on — ONE seam, deliberately.

    A COPY of ``img``, never an alias of it: a caller that needs the reconstruction to write through
    a buffer it already holds is a different shape and must not come here.

    SEVEN CALL SITES, and the number is grepped rather than remembered
    (``grep -rn 'candidate_image(' tools projects --include='*.py'``): this module's ``differential``
    and its attribution pass, and five in Wonder Boy — ``leaf.run_candidate_only`` plus the four
    enumerations that drive the candidate directly with no oracle beside them (``test_behavior.py``'s
    65,536 raw type values, its 256 swoop states and its 256 pickup indices, and ``test_sound.py``'s
    refusal stepping). Those four matter most: they are the WILDEST pointers any case computes, so a
    census taken with them outside the seam would exclude exactly the cases most likely to leave the
    image. Each used to build its own ``ctypes`` array, which meant a tool wanting the candidate's
    image placed SOMEWHERE PARTICULAR had to wrap every glue and every runner instead of replacing
    one function — and a runner it missed ran unguarded while the tool reported a clean sweep.
    ``guarded_image.py`` is that tool and this is what it replaces.

    **SIX SITES IN THE SIBLING PROJECTS ARE STILL OUTSIDE IT**, registered rather than routed
    (Wonder Boy STATUS.md, batch 43 phase C): BuggyBoy's ``test_game_update_real_course.py``,
    ``test_object_dispatch_real.py``, ``test_obj_blit_engine.py`` and ``test_sound.py``, Joust's
    ``test_input.py`` and ``test_player.py``, plus BuggyBoy's ``render/atari/game_smoke.py``. Three of
    them ALIAS a caller's live buffer rather than copying one, so they are not this function's shape
    at all and need a second seam or a change of their own. A guarded sweep of either project would
    under-report until they are dealt with, and neither project has one.

    Never live twice at once: the attribution pass runs strictly after the plain one, and the four
    enumerations above hold their buffer across a loop that calls no differential — so a replacement
    is free to hand back the same storage every call. A new caller that breaks that must not use it.
    """
    return (ctypes.c_uint8 * IMAGE_SIZE).from_buffer(bytearray(img))


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


def _hw_refusal_hint():
    """Name the modeled hardware addresses the CANDIDATE was just refused, as a sentence, or ``""``.

    ``os_refused()`` is ONE tally shared by every refusing helper, so a candidate that called
    ``hw_read8()`` on an address this case never declared reds through ``_vet_no_os_refusal`` with a
    bare count and a list of causes that do not mention hardware at all — the reader is sent to look
    for a missing Bconstat gate. The candidate's own read ledger can say which address it was: a slot
    it read whose declared bit is clear was served a refusal, not a byte.

    An address OUTSIDE the modeled set is refused WITHOUT a ledger entry (shim.c records nothing for
    one either), so there is no slot to name — it is described instead, since a reconstruction
    calling ``hw_read8(0xff8604)`` is the other way to arrive here.
    """
    if not _has_hw_ledger:
        return ""
    known, count, slots = _lib.g_hw_file_known(), _lib.g_hw_log_count(), _lib.g_hw_log_slots()
    undeclared = sorted({emu.HW_ADDRS[slots[i]] for i in range(count)
                         if not known & (1 << slots[i])})
    if not undeclared:
        return ""
    return (f" THE CANDIDATE READ MODELED HARDWARE THIS CASE DOES NOT DECLARE: "
            f"{', '.join(f'{addr:#x}' for addr in undeclared)}. Either the case is missing "
            f"hw_seed={{{', '.join(f'{addr:#x}: <byte>' for addr in undeclared)}}}, or the "
            f"reconstruction reads an address the original does not (TRAP_MODEL.md, Phase 7). "
            f"An hw_read8() of an address outside the modeled set refuses here too, and leaves no "
            f"ledger entry to name.")


def _sched_refusal_hint():
    """The clause `_vet_no_os_refusal` adds when a refused run's cause was the WAIT model.

    `os_refused()` is one tally shared by every refusing helper, so a bare count sends the reader
    hunting for a missing Bconstat gate. The two scheduled-write causes are by far the likeliest in
    a case that declares a schedule, and each has a remedy of its own — the same shape
    `_hw_refusal_hint` gives the hardware model.

    They are reported TOGETHER, `_vet_no_os_refusal`'s own rule: an undeclared site's poll returns
    the byte, so a wait at one usually ALSO runs to the cap, and naming only the cap would send the
    reader after the store's value when the site list is what is wrong.
    """
    if not _has_sched:
        return ""
    clauses = []
    if _lib.g_sched_undeclared():
        declared = ", ".join(f"site {i}: {_lib.g_sched_site_polls(i)} poll(s)"
                             for i in range(_lib.g_sched_site_count())) or "(none)"
        clauses.append(
            f" {_lib.g_sched_undeclared()} of them were a POLL AT A SITE THIS CASE DID NOT DECLARE: "
            f"the run's declared sites took {declared}"
            f", and the reconstruction called sched_poll8/sched_poll16 naming another PC. A poll "
            f"nobody counts is the hole the sites close (os.h, \"WAIT SITES\"), so it is refused "
            f"rather than served. Either the case is missing that PC from `wait_sites=`, or the "
            f"reconstruction names a site the original's wait does not re-execute.")
    if _lib.g_sched_exhausted():
        clauses.append(
            f" {_lib.g_sched_exhausted()} of them were a WAIT that ran to os.h's OS_SCHED_POLL_MAX "
            f"without its byte arriving, after {_lib.g_sched_polls()} poll(s): the case's schedule "
            f"never released it. Check the store's value against the byte the wait compares, and "
            f"the trigger PC against the instruction the wait re-executes.")
    return "".join(clauses)


def _vet_no_os_refusal(entry):
    """Reject a run in which the CANDIDATE made an os_* call the TOS model refuses — a FALSE GREEN.

    Call it after EVERY candidate run, the poison pass included — a refusal reached only on the
    poisoned image is the same untested-but-green case.

    The oracle's own tally is necessarily zero here: a refused trap sets ``g_unmodeled`` and
    ``emu.run()`` raises long before the diff. So any candidate-side refusal is an asymmetry, and it
    is the one that hides a missing guard (include/os.h, "refusing a call, on BOTH sides"). The
    seeded PSG model's refusal routes here too (``psg_port_read`` of an undeclared register), where
    the oracle's lives in its own counter — same asymmetry, and the remedy is named below.
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
        f"this case needs the state staged (harness.console_key(), harness.stage_files(), "
        f"psg_seed={{reg: value}} for a PSG register the candidate reads back) so BOTH sides execute "
        f"the call; or a stop_pc checkpoint ended the oracle before a call the candidate still "
        f"makes. See tools/recreate_kit/TRAP_MODEL.md."
        + _hw_refusal_hint() + _sched_refusal_hint())


def _vet_audio_capture_off(entry):
    """Reject a differential run made while the oracle's AUDIO-CAPTURE mode is armed — a FALSE GREEN.

    The mode (``emu.audio_capture``, tools/recreate_kit/TRAP_MODEL.md) serves a handful of hardware
    reads the oracle otherwise refuses: the ``$ff8800`` register read-back and the 50 Hz colour-ST
    tempo bytes. Every one of those answers is ``shim.c``'s invention rather than the game's data, so
    a reconstruction that agreed with the oracle across one would be verified against ``shim.c`` —
    which is the exact class of false green the refusals exist to close. The mode is for an
    extraction tool that runs the ORIGINAL only; it is never valid for a differential.

    It is process-global oracle state, so nothing about the CASE says whether it is armed — an
    extractor, or a case that raised before disarming, is enough. Hence a vet here rather than a
    convention. It is deliberately NOT in ``emu.run()``: a bare ``run()`` with the mode on is exactly
    what an extractor does, and is the whole point of the mode.
    """
    if not emu.audio_capture_on():
        return
    raise AssertionError(
        f"function @ {entry:#x}: the oracle's opt-in AUDIO-CAPTURE mode is armed, so this "
        f"differential would compare the candidate against reads shim.c FABRICATED — the $ff8800 "
        f"register-file read-back and the 50 Hz colour-ST tempo bytes ($fffa01 bit 7 / $ff820a bit "
        f"1) — instead of against the game's own data. A green result would mean the reconstruction "
        f"agrees with tools/recreate_kit/oracle/shim.c, not that it agrees with the original. Turn "
        f"the mode off before running a differential: `emu.audio_capture(False)`, or scope it with "
        f"`with emu.audio_capturing():` so it cannot leak out of the block that needed it. See "
        f"tools/recreate_kit/TRAP_MODEL.md.")


def _seed_candidate(reset, encode, seed, available):
    """Install one model's seed in the candidate and clear its ledger — the shape BOTH use.

    Called before EVERY candidate run, the poison re-run included, exactly as ``emu.run`` re-seeds
    the oracle before every run. A candidate left holding the previous case's state could read
    something it never declared and stay green on it, which is the whole false green these models
    close; and a ledger left holding the previous run's entries would be compared against this run's
    oracle stream. ``encode`` is the oracle's own encoder (``emu.psg_seed_bytes`` /
    ``emu.hw_seed_bytes``), so the two sides cannot disagree about what the case's dict means.

    ``available`` is the optional-ABI flag: a candidate without the group is left alone here and
    refused later, by the vet that has the oracle's own traffic as its witness.
    """
    if not available:
        return
    values, known = encode(seed)
    reset((ctypes.c_uint8 * len(values))(*values), known)


def _seed_candidate_psg(psg_seed):
    """Install the case's PSG seed (``{register: value}``) in the candidate. See _seed_candidate."""
    _seed_candidate(_lib.g_psg_reset if _has_psg_ledger else None,
                    emu.psg_seed_bytes, psg_seed, _has_psg_ledger)


def _vet_declared_state_matches(entry, what, oracle_bytes, oracle_known, cand_file, cand_known, why):
    """Compare one model's off-image byte file (and its known-mask) against the candidate's.

    Shared by both seeded models, because the comparison is one rule: given equal seeds both sides
    hold equal bytes BY CONSTRUCTION, so what this can catch is not the reconstruction but the two
    model IMPLEMENTATIONS drifting — a register-width mask added on one side, a slot numbering
    changed, capture state leaking into a differential. The known-mask travels with the bytes since
    "declared 0" and "never declared" are different chips.

    ``cand_file`` is read through a cast sized from the ORACLE's own file, so the two sides cannot
    disagree about the length; ``why`` is the model-specific consequence, which is the half of the
    message a reader acts on.
    """
    if (oracle_bytes, oracle_known) == (cand_file, cand_known):
        return
    raise AssertionError(
        f"function @ {entry:#x}: {what} diverged — oracle={oracle_bytes.hex()} "
        f"(known {oracle_known:#06x}) cand={cand_file.hex()} (known {cand_known:#06x}). {why}")


def _candidate_bytes(accessor, length):
    """``length`` bytes from a candidate ``const uint8_t *`` export, sized by its caller."""
    return bytes(ctypes.cast(accessor(), ctypes.POINTER(ctypes.c_uint8 * length)).contents)


def _vet_ledger_below_cap(what, oracle_entries, cand_entries, cap, const_name):
    """Refuse a comparison of two off-image ledgers that reached their shared cap.

    Both sides stop logging SILENTLY there, so two streams that diverge only past it truncate to the
    same list and compare EQUAL — a green that means "we stopped looking". One rule for both models
    (Phases 6 and 7), because it is a property of the ledger protocol rather than of either chip.

    Deliberately over-strict AT the cap: an oracle ledger of exactly `cap` entries is complete (its
    own dropped-counter would already have raised in emu.run), but the candidate has no such counter
    and genuinely cannot tell full from truncated, so both take the same bound. The cost is a loud
    false red on a run with exactly `cap` accesses. A bare `assert` would vanish under `python -O`,
    taking the guard with it; this is a raise. (The Dosound ledger keeps its own bare `assert` —
    it predates this and is deliberately left alone.)
    """
    if oracle_entries < cap and cand_entries < cap:
        return
    raise AssertionError(
        f"the {what} ledger hit its cap ({cap}): oracle={oracle_entries} cand={cand_entries} — the "
        f"compare beyond it would be blind; shorten the run or raise {const_name} in include/os.h "
        f"(its mirror in harness.py is pinned to it)")


def _vet_write_ledger_below_cap(entry, o_regs):
    """Refuse a differential whose ORACLE run filled the write ledger.

    `shim.c`'s `logw` saturates at `emu.MAX_WRITES` write events and counts nothing past it, so the
    write set `emu.run` hands back is truncated without saying so — and a truncated write set is
    exactly the input a band check reads as "the run wrote nowhere else". That is the same class of
    blind green `_vet_ledger_below_cap` refuses one tier down for the two off-image ledgers.

    HERE AND NOT IN `emu.run`, deliberately. Truncation fabricates nothing: the final memory is the
    run's own and so is every register. A bare `emu.run` caller that never looks at the write set is
    therefore served — a Copylock run into the blob fills the ledger honestly and is compared on its
    MEMORY (projects/wonderboy's test_copylock.py). A DIFFERENTIAL is where a write set becomes a
    claim, so this is where it is refused. The split, and its precedent, are stated in `emu.run`.
    """
    if not o_regs.get("writes_truncated"):
        return
    raise AssertionError(
        f"the oracle run of {entry:#x} filled the write ledger ({emu.MAX_WRITES} events; shim.c's "
        f"MAX_WRITES) and the rest were dropped, so its write set is truncated and any band check "
        f"made against it would be blind past the cap. Shorten the run — a stop_pc earlier in the "
        f"routine — or raise MAX_WRITES in tools/recreate_kit/oracle/shim.c (its mirror in "
        f"oracle/emu.py is pinned to it by hand)")


def _psg_event_text(events):
    """One ledger's events as readable text: ``r7=0xc0`` for a write, ``r7->0xc0`` for a read."""
    return [f"r{reg}{'=' if kind == OS_PSG_EVENT_WRITE else '->'}{value:#04x}"
            for kind, reg, value in events]


def _vet_psg_seed_reaches_the_path(entry, psg_seed, pokes, o_regs):
    """Refuse a case whose ``psg_seed`` declares state the run it describes never reads.

    ONE chip, TWO doors, and the seed only opens one of them (TRAP_MODEL.md, "One chip, three
    files"). ``psg_seed=`` declares the DIRECT path's off-image register file; ``psg_regs()`` stages
    the file XBIOS ``Giaccess`` reads, which lives in the image. The two arguments look identical at
    a call site — both are ``{register: byte}`` — and picking the wrong one is silent: the seed is
    installed, nothing reads it, and the case passes while testing the read-back it meant to stage
    not at all. Two shapes of that mistake, refused here because nothing downstream can see them:

    * **both doors at once.** A case that seeds AND pokes ``OS_PSG_REGS`` is describing one chip's
      contents twice, in two models that never see each other's stores — and a run that actually
      reached both would be refused by the mixed-path guard anyway.
    * **the seed goes unread while ``Giaccess`` runs.** The run made no direct access at all, so the
      seed cannot have been read by anything; that it also called ``Giaccess`` says which door the
      routine really uses.

    A seed unread by a run that touches NEITHER path is left alone: an over-declared input is
    ordinary (a case that seeds a register the branch it takes never reads), and refusing it would
    make the seed a claim about control flow rather than about the chip.
    """
    if psg_seed is None:
        return
    psg_file_end = OS_PSG_REGS + OS_PSG_NREGS
    overlapping = sorted(addr for addr, value in (pokes or {}).items()
                         if OS_PSG_REGS < addr + len(value) and addr < psg_file_end)
    if overlapping:
        raise AssertionError(
            f"function @ {entry:#x}: this case passes psg_seed={psg_seed} AND pokes the "
            f"Giaccess register file at {', '.join(hex(a) for a in overlapping)} "
            f"(harness.psg_regs / OS_PSG_REGS {OS_PSG_REGS:#x}). Those are the YM2149's TWO "
            f"doors and they are separate models: psg_seed declares the direct $ff8800/$ff8802 "
            f"path's off-image register file, psg_regs() stages the in-image file the XBIOS trap "
            f"reads, and neither sees the other's stores. Declare the one the routine actually uses "
            f"— a run that reached both would be refused by the mixed-path guard (TRAP_MODEL.md, "
            f"Phases 3 and 6).")
    if not o_regs["psg_direct"] and o_regs["psg_giaccess"]:
        raise AssertionError(
            f"function @ {entry:#x}: this case passes psg_seed={psg_seed}, but the run "
            f"made no direct $ff8800/$ff8802 access at all — so nothing read the seed — while "
            f"issuing {o_regs['psg_giaccess']} XBIOS Giaccess call(s). This routine reaches the chip "
            f"through the TRAP path, whose register file is staged with harness.psg_regs() and lives "
            f"IN the image; psg_seed is the direct path's, and here it declares state no instruction "
            f"in the run can see. Stage the other door (TRAP_MODEL.md, Phases 3 and 6).")


def _vet_psg_state(entry, o_regs):
    """Compare the direct PSG path's two off-image surfaces against the candidate's (src/psg.c).

    Neither is in the image, so neither is covered by the byte diff: a reconstruction could skip a
    register access, write the wrong value, order them wrongly, ignore a read-back it should have
    merged, or READ THE WRONG REGISTER, and the memory comparison would see nothing. The LEDGER
    catches all of those — which is why it carries reads as well as writes. A transposed
    read-modify-write is the case that forced it: read register 8, merge, write register 7, where
    register 8 happens to hold what 7 did. Its write stream is a correct run's, byte for byte, and so
    is the register file it leaves; only the read entry separates the two.

    The FILE is a CROSS-CHECK of the two implementations rather than extra coverage of the
    reconstruction: both sides store into it on exactly the writes they log, so under equal seeds an
    equal ledger already implies an equal file. What it can catch is the two model implementations
    themselves drifting — a register-width mask added on one side, capture-mode state leaking into a
    differential — which is the one thing the ledger comparison cannot see. It is compared with the
    known-register mask, since "written 0" and "never written" are different chips.

    The group is optional ABI (see ``_has_psg_ledger``) with the oracle's own traffic as the witness:
    a candidate without it is served only while the oracle never touches the path, exactly as for the
    Dosound ledger. The witness is the oracle's direct-ACCESS tally rather than its ledger's write
    projection, because a run that only READS the chip writes no register — and a candidate that
    hardcoded what it should have read is exactly what this exists to catch.
    """
    o_psg = o_regs["psg_events"]
    if not _has_psg_ledger:
        if o_regs["psg_direct"]:
            raise AssertionError(
                f"the oracle made {o_regs['psg_direct']} direct PSG access(es) but {_CFG.name}'s "
                f"candidate exports no {'/'.join(_missing_psg_ledger)} — neither the register "
                f"stream nor the chip state can be compared, so a divergence in either would pass "
                f"unnoticed. That is tools/recreate_kit/src/psg.c's ABI: build the candidate "
                f"through kit.mk, whose SRC sweeps $(KIT)/src/*.c")
        return

    count = _lib.g_psg_log_count()
    kinds, regs, vals = _lib.g_psg_log_kinds(), _lib.g_psg_log_regs(), _lib.g_psg_log_vals()
    c_psg = [(kinds[i], regs[i], vals[i]) for i in range(count)]
    _vet_ledger_below_cap("direct-PSG", len(o_psg), count, OS_PSG_LOG_MAX, "OS_PSG_LOG_MAX")
    if o_psg != c_psg:
        raise AssertionError(
            f"function @ {entry:#x}: direct-PSG access stream mismatch — "
            f"oracle={_psg_event_text(o_psg)} cand={_psg_event_text(c_psg)} "
            f"(`rN=v` wrote v to register N, `rN->v` read v back from it). The $ff8800/$ff8802 "
            f"ports are outside the image, so this divergence is invisible to the byte diff")

    # Sized from the oracle's own file, so the two casts cannot disagree about the register count.
    _vet_declared_state_matches(
        entry, "the modeled YM2149 register file", o_regs["psg_file"], o_regs["psg_known"],
        _candidate_bytes(_lib.g_psg_file, len(o_regs["psg_file"])), _lib.g_psg_file_known(),
        "That file is what a read-back answers from, so the next run of this driver would be served "
        "different bytes on the two sides")


def _seed_candidate_hw(hw_seed):
    """Install the case's hardware seed (``{address: byte}``) in the candidate. See _seed_candidate."""
    _seed_candidate(_lib.g_hw_reset if _has_hw_ledger else None,
                    emu.hw_seed_bytes, hw_seed, _has_hw_ledger)


def _vet_schedule_is_runnable(entry, schedule, wait_sites):
    """Refuse a differential whose schedule the CANDIDATE cannot mirror — before either side runs.

    Two shapes. An ``insn`` trigger names an instruction index, and the candidate has no instruction
    counter at all: the oracle would make the store and the candidate would spin, which reads as a
    hung test rather than as a case that could never have worked. And a schedule against a candidate
    with no ``src/sched.c`` linked is the same thing one level down — the entries would fire on the
    oracle alone, and every byte the agent supplied would come back as a diff against a reconstruction
    that never saw it.

    A THIRD SHAPE USED TO BE REFUSED HERE AND IS NOT ANY MORE: a schedule naming more than one
    trigger PC. It was refused because both sides counted a run TOTAL, which two waits can balance by
    cancellation; the counts are now kept PER WAIT SITE on both shores (os.h, "WAIT SITES"), so two
    waits in one run are an ordinary case. What replaces it is stricter and lives in the encoder —
    every trigger PC must be a declared site (``emu.wait_site_pcs``), and a poll at an undeclared
    site is refused by ``sched_poll8`` — so a wait can no longer go uncounted at all.
    """
    if not schedule and not wait_sites:
        return
    if not _has_sched:
        raise AssertionError(
            f"the case for {label(entry)} @ {entry:#x} declares a scheduled write, but "
            f"{_CFG.name}'s candidate exports no {'/'.join(_missing_sched_abi)} — "
            f"tools/recreate_kit/src/sched.c is not linked into it, so the agent's store would be "
            f"made on the ORACLE side only and every byte it supplied would read as a divergence. "
            f"Build the candidate through kit.mk, whose SRC sweeps $(KIT)/src/*.c.")
    # SHAPE FIRST. The trigger-set test below indexes `spec["pc"]`, so an entry that names neither
    # trigger — or both — would come out of here as a bare KeyError naming nothing. emu's encoder
    # owns every field's shape and its messages say what is wrong; run them before reading a key.
    emu.schedule_entries(schedule)
    at_insn = [i for i, spec in enumerate(schedule or ()) if "insn" in spec]
    if at_insn:
        raise AssertionError(
            f"the case for {label(entry)} @ {entry:#x} schedules entr(ies) {at_insn} on an `insn` "
            f"trigger, which a differential cannot run: the candidate is C and counts POLLS, not "
            f"instructions, so nothing on that side could fire the store at the same moment. Give "
            f"the entry a `pc` trigger — the address of the instruction the original's wait loop "
            f"re-executes — and have the reconstruction read that byte through `sched_poll8`. The "
            f"`insn` trigger is for an oracle-only run (emu.run).")
    # ...and every trigger PC must be a declared WAIT SITE, which the encoder owns because the site
    # list is what both shores key their counters by. Run it here so the case is refused before
    # either core does, with the encoder's own wording.
    emu.wait_site_pcs(schedule, wait_sites)


def _seed_candidate_sched(scheduled, sites):
    """Install the run's schedule in the candidate — the SAME flattened array and the SAME wait-site
    list the oracle was given.

    Unconditional, an empty schedule included, for ``_seed_candidate``'s reason: a list left over
    from the previous case would fire inside this one, and under ``-n auto`` which case that was is
    not stable.
    """
    if not _has_sched:
        return
    n = len(scheduled) // emu.SCHED_FIELDS
    _lib.g_sched_reset(emu.schedule_array(scheduled), n,
                       emu.schedule_array(list(sites)), len(sites))
    # The candidate CLAMPS to OS_SCHED_MAX/OS_SCHED_SITE_MAX and reports what it kept. The encoders
    # refuse an over-long list one level up, so these can only fire if the two sides disagree about
    # a cap — and a schedule silently carrying fewer stores or sites than the case declared reads as
    # a wait loop that simply never ended, which is the worst diagnostic in this model.
    assert _lib.g_sched_count() == n, (
        f"the candidate kept {_lib.g_sched_count()} of the run's {n} scheduled store(s) — its "
        f"OS_SCHED_MAX and the harness's disagree")
    assert _lib.g_sched_site_count() == len(sites), (
        f"the candidate kept {_lib.g_sched_site_count()} of the run's {len(sites)} wait site(s) — "
        f"its OS_SCHED_SITE_MAX and the harness's disagree")


def _vet_schedule_ran_the_same_wait(entry, o_regs):
    """Compare the ORACLE's arrivals against the CANDIDATE's polls, WAIT SITE BY WAIT SITE.

    This is the whole cross-check the model rests on. The store itself is applied from the same list
    on both sides, so a port that spun a different number of times — or did not spin at all, or
    polled a byte the original reads outside the loop — still ends with identical memory and would
    pass the diff. The counts are what separate them: one arrival at the compare is one poll.

    PER SITE, AND THAT IS THE LOAD-BEARING WORD — but it is the FIRING rule that carries the catch,
    not this comparison, and saying so is the honest reading of the measurement. Against run TOTALS a
    run with two waits balances by cancellation: the candidate's store fires an iteration early on
    the second wait and the first wait's poll makes the sum up, so a port that DELETED the first wait
    matches (os.h, "WAIT SITES"; Wonder Boy's `flip_screen` is the arrangement). Keying the FIRING to
    the site is what breaks that — the entry now comes due on its own site's count, so the two sides'
    totals diverge as well.

    THIS COMPARISON IS AN UNPROVEN TRIPWIRE, with the standing the kept-count assertions have. Two
    composites were written to isolate it — the comparison removed beside the deleted first wait, and
    beside a port that moves a poll from one site to the other — and BOTH came back caught by the
    firing rule instead. No input is known that only this line catches. It stays because the day the
    firing rule stops being what it is, this is what would notice; it is not claimed as covered.
    (projects/wonderboy/recreate/STATUS.md, batch 42 phase C.) The totals are asserted below too,
    which costs nothing and catches a site list the two sides somehow ordered differently.
    """
    if not _has_sched or not (o_regs.get("sched") or o_regs.get("sched_sites")):
        return
    sites = o_regs["sched_sites"]
    site_arrivals = o_regs["sched_site_arrivals"]
    site_polls = tuple(_lib.g_sched_site_polls(i) for i in range(len(sites)))
    assert site_arrivals == site_polls, (
        f"{label(entry)} @ {entry:#x}: the two sides ran different wait loops — "
        + ", ".join(f"site {pc:#x}: oracle {a} arrival(s), candidate {p} poll(s)"
                    for pc, a, p in zip(sites, site_arrivals, site_polls))
        + ". Poll exactly the byte the original's compare reads, once per iteration, naming that "
          "compare's own PC as the site, and nothing else (see include/sched.h).")
    arrivals, polls = o_regs["sched_arrivals"], _lib.g_sched_polls()
    assert arrivals == polls, (
        f"{label(entry)} @ {entry:#x}: the oracle arrived at a declared wait site {arrivals} "
        f"time(s) and the candidate polled {polls} time(s) while agreeing site by site — the two "
        f"sides are not reading the same site list in the same order")
    applied, refused = _lib.g_sched_applied(), _lib.g_sched_refused()
    assert (applied, refused) == (o_regs["sched_applied"], 0), (
        f"{label(entry)} @ {entry:#x}: the agent made {o_regs['sched_applied']} store(s) on the "
        f"oracle and {applied} on the candidate ({refused} refused) from the same schedule — the "
        f"two sides did not model the same external write")


def _hw_event_text(events):
    """One ledger's reads as readable text: ``0xfffa01->0xb0``."""
    return [f"{addr:#x}->{value:#04x}" for addr, value in events]


def _hw_seed_text(hw_seed):
    """A case's ``hw_seed`` as a reader would type it: ``{0xfffa01: 0xb0}``, or a prescription when
    there is none.

    Python renders a dict of ints in DECIMAL, so the raw form of a hardware seed comes out
    ``{16775681: 176}`` — a reader cannot match that against the address in the disassembly, which is
    the one thing a refusal message exists to let them do. And an absent seed rendered as ``None``
    puts "hw_seed=None declares what the machine held on entry" in a message whose whole point is
    that it does not.
    """
    if not hw_seed:
        return "no hw_seed was given, and a seed is what declares"
    body = ", ".join(f"{addr:#x}: {value:#04x}" for addr, value in sorted(hw_seed.items()))
    return f"hw_seed={{{body}}} declares"


def _vet_hw_reads_are_declared(entry, hw_seed, o_regs):
    """Refuse a differential whose ORACLE read a modeled hardware byte the case never declared.

    **THIS IS PHASE 7'S REFUSAL, AND IT LIVES HERE RATHER THAN IN ``emu.run``** — the one place its
    contract differs from Phase 6's, deliberately. An undeclared PSG read sinks the run inside
    ``emu.run``, so it is refused for every caller. An undeclared *hardware* read is served the 0 it
    has always been served there, and only a DIFFERENTIAL refuses it. Two reasons, and they are the
    whole design:

    * a bare ``emu.run`` is how this workspace drives a game's relocator, its Copylock and its
      bootstrap (``test_copylock.py``, ``test_bootstrap.py``). Those touch hardware nobody has
      enumerated, and an always-on refusal would sink runs that verify nothing and so cannot be
      falsely green;
    * a false green needs something being VERIFIED. That is exactly what a differential is: the
      candidate and the oracle agreeing on a branch that a fabricated 0 chose for both of them,
      which is the ``$ffff820a`` defect BuggyBoy shipped green.

    Four shapes are refused, each with its own remedy, and they are tested NARROWEST FIRST:

    * **stale** — the run WROTE the address and then read it back. The seed declares what the
      machine held on ENTRY, and an instruction of this very run has replaced it, so the served byte
      contradicts the program. Not seedable: end the case before the write, or start after it.
      One read can be stale *and* undeclared, and reporting that as "declare it" sends the reader to
      add a ``hw_seed`` and hit the un-seedable refusal on the next run — so stale is diagnosed
      first, being the strictly narrower answer;
    * **wide** — a 16- or 32-bit read took the byte in along with neighbouring registers the model
      knows nothing about, which it would have to fabricate as 0. Also not seedable, and also
      possible alongside an undeclared byte-read of the same address;
    * **volatile re-read** — the run read a VOLATILE address (``os.h``'s ``os_hw_volatile_slots()``:
      the shifter's video-counter bytes) more than once, and a seed is a per-run CONSTANT, so the
      second read was served the first read's byte. Not seedable either — one number cannot be two:
      end the case before the second read, or split it into two runs. A STATIC address is exempt:
      the machine's answer is the same every time, so one declaration describes every read of it;
    * **undeclared** — nothing said what the byte holds. Declare it with ``hw_seed=``.
    """
    if o_regs["hw_stale"]:
        written = o_regs["hw_stale"]
        raise AssertionError(
            f"function @ {entry:#x}: the oracle WROTE the modeled hardware byte(s) "
            f"{', '.join(f'{addr:#x}' for addr in written)} and then READ one back. "
            f"{_hw_seed_text(hw_seed)} what the machine held on ENTRY, and an instruction of this "
            f"run has replaced it — the model drops hardware writes, so the read would be served "
            f"the entry byte and contradict the program. Adding one cannot fix it: run the case up "
            f"to the write, or enter past it with the seed describing what the write left "
            f"(TRAP_MODEL.md, Phase 7).")
    if o_regs["hw_wide"]:
        wide = o_regs["hw_wide"]
        raise AssertionError(
            f"function @ {entry:#x}: the oracle read the modeled hardware byte(s) "
            f"{', '.join(f'{addr:#x}' for addr in wide)} as part of a 16- or 32-bit access. Only a "
            f"BYTE read of one is served — a wider one takes in the neighbouring MFP/shifter "
            f"registers, which the model would have to fabricate as 0, and the case would be "
            f"verified against that fabrication. Not seedable either: the width is an instruction.")
    if o_regs.get("hw_reread"):
        repeated = o_regs["hw_reread"]
        raise AssertionError(
            f"function @ {entry:#x}: the oracle read the VOLATILE hardware byte(s) "
            f"{', '.join(f'{addr:#x}' for addr in repeated)} MORE THAN ONCE in one run. A seed is "
            f"a per-run CONSTANT, so the second read was served the first read's byte — and the "
            f"machine changes these on its own (the shifter's video counter advances every few "
            f"scanlines), so the case would be verified against a value the address cannot have "
            f"held twice. A volatile byte cannot be served twice from one declaration: end the "
            f"case before the second read, or split it into two runs each declaring what the "
            f"counter held then (TRAP_MODEL.md, Phase 7). os.h's os_hw_volatile_slots() names "
            f"which slots these are.")
    if o_regs["hw_unseeded"]:
        undeclared = o_regs["hw_unseeded"]
        raise AssertionError(
            f"function @ {entry:#x}: the oracle READ the modeled hardware byte(s) "
            f"{', '.join(f'{addr:#x}' for addr in undeclared)}, which this case does not declare — "
            f"so both sides were served a fabricated 0 and would agree on whatever branch it "
            f"chooses. That agreement is the false green this model exists to close (the $ffff820a "
            f"music-tempo branch BuggyBoy shipped, invisible to its whole differential). Declare "
            f"the byte the machine really holds, as the input it is: "
            f"hw_seed={{{', '.join(f'{addr:#x}: <byte>' for addr in undeclared)}}} "
            f"(TRAP_MODEL.md, Phase 7).")


def _vet_hw_state(entry, o_regs):
    """Compare the seeded hardware model's ordered READ stream — and its declared bytes — against
    the candidate's (``src/hw.c``).

    Nothing here is in the image, so nothing else could catch a divergence. A reconstruction that
    read the WRONG modeled address, read one it should not have, or skipped a read the original
    makes, writes exactly the same bytes as a correct one whenever the branch happens to land the
    same way — and the byte diff sees nothing either way. The ordered stream is the only witness.

    The FILE is a cross-check of the two implementations rather than extra coverage: under equal
    seeds both sides hold the same declared bytes by construction, so what it can catch is the two
    models drifting — a slot numbering changed on one side, the capture profile leaking into a
    differential. It is compared with the known-mask, since "declared 0" and "never declared" are
    different machines.

    Optional ABI (``_has_hw_ledger``) with the oracle's own read stream as the witness, exactly as
    for the PSG ledger: a candidate without it is served only while the oracle reads no modeled
    address at all.
    """
    o_hw = o_regs["hw_events"]
    if not _has_hw_ledger:
        if o_hw:
            raise AssertionError(
                f"the oracle read {len(o_hw)} modeled hardware byte(s) but {_CFG.name}'s candidate "
                f"exports no {'/'.join(_missing_hw_ledger)} — neither the read stream nor the "
                f"declared bytes can be compared, so a reconstruction reading the wrong one, or "
                f"none, would pass unnoticed. That is tools/recreate_kit/src/hw.c's ABI: build the "
                f"candidate through kit.mk, whose SRC sweeps $(KIT)/src/*.c")
        return

    count = _lib.g_hw_log_count()
    slots, vals = _lib.g_hw_log_slots(), _lib.g_hw_log_vals()
    c_hw = [(emu.HW_ADDRS[slots[i]], vals[i]) for i in range(count)]
    _vet_ledger_below_cap("seeded-hardware read", len(o_hw), count, OS_HW_LOG_MAX, "OS_HW_LOG_MAX")
    if o_hw != c_hw:
        raise AssertionError(
            f"function @ {entry:#x}: modeled hardware read stream mismatch — "
            f"oracle={_hw_event_text(o_hw)} cand={_hw_event_text(c_hw)} "
            f"(`0xfffa01->0xb0` read 0xb0 from 0xfffa01). These addresses are outside the image, "
            f"and so is the branch they steer, so this divergence is invisible to the byte diff")

    _vet_declared_state_matches(
        entry, "the declared hardware bytes", o_regs["hw_file"], o_regs["hw_known"],
        _candidate_bytes(_lib.g_hw_file, len(o_regs["hw_file"])), _lib.g_hw_file_known(),
        "The two sides were handed the same hw_seed, so this is the two model implementations "
        "disagreeing, not the reconstruction")


def _vet_poison_is_attributable(entry, scheduled, o_writes):
    """Refuse an attribution pass whose canary a SCHEDULED STORE would overwrite.

    The pass poisons every oracle-written byte and re-runs both cores, so a byte the candidate
    failed to write stays canary. The agent's store is applied from the same list on both sides and
    lands BEFORE the function's own store, so a byte that is both scheduled and written comes out
    correct on both sides whether or not the reconstruction wrote it — the pass then reports an
    attribution nobody made, which is worse than not running it.

    Wonder Boy's two waits are exactly this shape (`clr.b $879.l` over the byte the schedule
    releases) and pass ``poison=False`` with seeded destinations instead; this is what stops the
    next such case doing it by accident.
    """
    if not scheduled:
        return
    fields = emu.SCHED_FIELDS
    stored = {scheduled[i + emu.OS_SCHED_F_ADDR] + byte
              for i in range(0, len(scheduled), fields)
              for byte in range(scheduled[i + emu.OS_SCHED_F_WIDTH])}
    clash = sorted(stored & set(o_writes))
    assert not clash, (
        f"{label(entry)} @ {entry:#x}: the attribution pass would poison "
        f"{', '.join(f'{addr:#x}' for addr in clash)}, which this run's schedule also stores — the "
        f"agent overwrites the canary on both sides, so the pass would pass whatever the candidate "
        f"wrote. Use poison=False and seed those destinations away from what the routine leaves.")


def _attribution_check(img, entry, regs, glue, o_final, o_writes, guard_lo, excluded,
                       stop_pc, max_insns, psg_seed, hw_seed, schedule, wait_sites):
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
    po_final, _, po_regs = emu.run(poisoned, entry, regs, stop_pc=stop_pc, max_insns=max_insns,
                                   psg_seed=psg_seed, hw_seed=hw_seed, schedule=schedule,
                                   wait_sites=wait_sites)
    # Poisoning can steer the ORACLE into a modeled hardware read the plain run never made, and one
    # the case does not declare would be served a fabricated 0 on this pass too.
    _vet_hw_reads_are_declared(entry, hw_seed, po_regs)
    buf = candidate_image(poisoned)
    # This is a SECOND candidate run, so it needs the same per-run bookkeeping the first one got:
    # poisoning inverts oracle-written bytes, which can steer the candidate down a path the plain
    # run never took — including into a refused os_* call, or into PSG traffic. Reset before, vet
    # after, or that refusal is tallied into a count nobody reads and the pass reports a clean
    # attribution.
    _lib.g_os_refusal_reset()
    _seed_candidate_psg(psg_seed)
    _seed_candidate_hw(hw_seed)
    _seed_candidate_sched(po_regs["sched"], po_regs["sched_sites"])
    glue(_lib, buf)
    _vet_no_os_refusal(entry)
    # ...and the same off-image PSG comparison the plain pass got, against the POISONED run's own
    # oracle surfaces. Poisoning can steer either core into different register traffic, and that
    # traffic is invisible to the byte compare below — which is the whole reason this pass exists.
    _vet_psg_state(entry, po_regs)
    _vet_hw_state(entry, po_regs)
    _vet_schedule_ran_the_same_wait(entry, po_regs)
    pc_final = bytes(buf)
    bad = [a for a in range(guard_lo) if po_final[a] != pc_final[a] and not excluded(a)]
    if bad:
        a = bad[0]
        raise AssertionError(
            f"attribution (poison) check: candidate diverges on a poisoned-output image at "
            f"{label(a)} @ 0x{a:x} (oracle={po_final[a]:#04x} cand={pc_final[a]:#04x}, {len(bad)} "
            f"bytes) — it likely never wrote a byte the oracle wrote, passing the plain diff by "
            f"coincidence")


def differential(entry, regs, glue, stop_pc=0, exclude=None, max_insns=200_000, poison=False,
                 psg_seed=None, hw_seed=None, schedule=None, wait_sites=None):
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
    (``_vet_no_os_refusal``) — such a case tests nothing, however clean its bytes look — or if the
    oracle's audio-capture mode is armed (``_vet_audio_capture_off``), which would verify the
    candidate against reads ``shim.c`` fabricated.
    ``poison`` runs an extra attribution pass (``_attribution_check``): re-run both cores on an
    image whose oracle-written bytes are pre-poisoned, catching a candidate that matches by
    coincidence without actually writing a byte the oracle wrote. Opt-in (safe for leaf functions).
    It is REFUSED over a byte the run's own ``schedule`` also stores: the agent's store lands on both
    sides from the same list and overwrites the canary, so a candidate that never made the
    function's store would match anyway and the pass would report an attribution it did not make.
    ``psg_seed`` is ``{register: value}``, the contents the case declares the YM2149 held on entry —
    an ordinary input, given identically to both sides, and what makes a read-modify-write of the
    chip runnable (``emu.run``; TRAP_MODEL.md, Phase 6). It is the DIRECT ``$ff8800``/``$ff8802``
    path's state, not the ``Giaccess`` file ``psg_regs()`` stages, and a case that confuses the two
    is refused (``_vet_psg_seed_reaches_the_path``). Both sides' register file and access ledger are
    compared afterwards, seed or none (``_vet_psg_state``).
    ``hw_seed`` is ``{address: value}`` over the modeled hardware set (``emu.HW_ADDRS``: the MFP
    GPIP byte, the shifter's sync byte and its two video-counter bytes), the same kind of declared
    input for a byte that steers a branch — or, for the counter pair, one a routine hashes into an
    arithmetic result (TRAP_MODEL.md, Phase 7). **A run whose oracle read one of them without a
    declaration is REFUSED here** — that refusal is a differential's, not ``emu.run``'s, and
    ``_vet_hw_reads_are_declared`` says why, along with the three other shapes it refuses (a stale
    read-back, a wide read, and a second read of a VOLATILE address, which one per-run constant
    cannot describe). Both sides' ordered read stream is compared afterwards, seed or none
    (``_vet_hw_state``).
    ``schedule`` is the list of stores an EXTERNAL AGENT makes while the run is in flight, for a
    routine that busy-waits on a byte its own instructions never write (``emu.schedule_entries``;
    TRAP_MODEL.md, Phase 8). The SAME list is installed on both sides, and the oracle's arrivals are
    compared against the candidate's ``sched_poll8`` calls afterwards
    (``_vet_schedule_ran_the_same_wait``) — without that the agent would make both sides' memory
    agree whatever the reconstruction's loop did.
    ``wait_sites`` names every PC this run busy-waits at, and defaults to the trigger PCs the
    schedule carries — which is right whenever the run holds ONE wait. Both counts above are kept
    per site, so a run with two waits is compared wait by wait instead of as two totals that can
    cancel (os.h, "WAIT SITES"). A run whose second wait the schedule does not store on has to name
    it here: the candidate's poll at an undeclared site is refused rather than uncounted.
    """
    _vet_audio_capture_off(entry)
    _vet_schedule_is_runnable(entry, schedule, wait_sites)
    pokes = regs.pop("_pokes", None)
    img = make_image(pokes)
    o_final, o_writes, o_regs = emu.run(img, entry, regs, stop_pc=stop_pc, max_insns=max_insns,
                                        psg_seed=psg_seed, hw_seed=hw_seed, schedule=schedule,
                                        wait_sites=wait_sites)

    _vet_exclude_bands(exclude, o_regs["min_a7"])
    _vet_write_ledger_below_cap(entry, o_regs)
    _vet_psg_seed_reaches_the_path(entry, psg_seed, pokes, o_regs)
    # Before the candidate runs at all: a case whose oracle was served a fabricated hardware byte
    # cannot be made honest by anything the candidate does, and the remedy names the seed to add.
    _vet_hw_reads_are_declared(entry, hw_seed, o_regs)

    buf = candidate_image(img)
    if _has_dosound_ledger:
        _lib.g_dosound_log_reset()       # fresh Dosound ledger for this candidate run (see below)
    _lib.g_os_refusal_reset()            # ...and a fresh refused-os_*-call tally (see below)
    _seed_candidate_psg(psg_seed)        # ...and the same PSG entry state the oracle just ran on
    _seed_candidate_hw(hw_seed)          # ...and the same declared hardware bytes
    # ...and the same external-agent stores, on the same declared wait sites
    _seed_candidate_sched(o_regs["sched"], o_regs["sched_sites"])
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

    _vet_psg_state(entry, o_regs)
    _vet_hw_state(entry, o_regs)
    _vet_schedule_ran_the_same_wait(entry, o_regs)

    if poison and not diffs:
        _vet_poison_is_attributable(entry, o_regs["sched"], o_writes)
        _attribution_check(img, entry, regs, glue, o_final, o_writes, guard_lo, excluded,
                           stop_pc, max_insns, psg_seed, hw_seed, schedule, wait_sites)

    return diffs, {"writes": o_writes, "regs": o_regs, "ret": cand_ret}


def report(diffs):
    return "\n".join(f"  {label(a)} (0x{a:x}): oracle={o:#04x} cand={c:#04x}" for a, o, c in diffs)