"""Bind one project's ``recreate/`` directory to the shared kit.

The kit's oracle modules (``loader``, ``emu``) are plain top-level modules living in
``recreate_kit/oracle/``, so every existing ``import emu`` / ``from loader import …`` keeps
working. They carry no game constants of their own: ``load()`` reads the project's
``project.toml``, rebinds ``loader.LOAD_BASE`` / ``loader.IMAGE_SIZE``, and only then may
``emu`` be imported (it derives its stack constants from ``loader.IMAGE_SIZE`` at import time).

Call it before importing anything from the kit:

    sys.path.insert(0, str(<reverse>/"tools"))
    from recreate_kit import project
    project.load(<path to projects/<game>/recreate>)
"""
import sys
from pathlib import Path
from types import SimpleNamespace

from . import os_map           # the poked-input block's extent, importable with nothing built

try:
    import tomllib                     # stdlib from Python 3.11
except ImportError:                    # 3.10 and older: the same parser, pre-stdlib
    import tomli as tomllib

KIT = Path(__file__).resolve().parent
ORACLE = KIT / "oracle"
CONFIG_NAME = "project.toml"

_CONFIG = None


def _bool_flag(raw, key, recreate_dir):
    """An optional project.toml flag that must be a real TOML boolean; False when absent.

    These flags waive safety checks, and every non-empty TOML string is truthy in Python — so
    ``tos_malloc_unused = "false"`` would silently *enable* the waiver it was written to disable.
    Refuse anything that is not a bool rather than interpret it.
    """
    if key not in raw:
        return False
    value = raw[key]
    if not isinstance(value, bool):
        raise TypeError(f"{recreate_dir / CONFIG_NAME}: `{key}` must be a TOML boolean "
                        f"(true/false), not {type(value).__name__} {value!r} — it waives a safety "
                        f"check, and a quoted value would be read as true")
    return value


def _address(raw, key, recreate_dir, why):
    """An optional address-valued key, or None when absent. SHAPE ONLY — every caller below.

    ``why`` completes the refusal: one clause saying what that particular address is handed to, so
    the message says more than "it is odd". Positive and EVEN is the shape every address in a
    project.toml has, because each one is either code a 68000 fetches or data it takes words out of
    — an odd one could only ever mean the author has the wrong number. Whether the address is a
    legal PLACE is ``harness._vet_os_memory_map``'s question, since only it knows the image.

    A quoted address is the plausible hand-edit and ``true`` the one an ``isinstance(int)`` test
    alone would let through — bool is a subclass of int, so a key set to ``true`` would install
    address 1.
    """
    if key not in raw:
        return None
    value = raw[key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{recreate_dir / CONFIG_NAME}: `{key}` must be a TOML integer address "
                        f"(0x30000, not \"0x30000\"), not {type(value).__name__} {value!r}")
    if value <= 0 or value % 2:
        raise ValueError(f"{recreate_dir / CONFIG_NAME}: `{key}` is {value:#x}; it must be a "
                         f"positive EVEN address — {why}")
    return value


def _heap_base(raw, recreate_dir):
    """The optional ``heap_base`` address, or None when absent (= the kit's own default).

    Where the modeled Malloc arena starts, for a project whose program covers the kit's default
    0x20000 — see "the Malloc arena's base" in ``include/os.h``. None rather than the default itself
    because the default is C's (``OS_HEAP_BASE_DEFAULT``, mirrored in ``oracle/emu.py``, which this
    module cannot import: ``emu`` imports *it*). ``emu`` resolves the two.

    Only the shape is checked here; whether the address is a legal PLACE — clear of the program and
    of the model's other fixed regions — is ``harness._vet_os_memory_map``'s question, because only
    it knows where the program ends. Odd is refused because a Malloc block base is handed straight
    to 68000 code, which takes a word from it: an odd arena would make every allocating run an
    address error on real hardware while the model, which emulates none, ran on regardless.
    """
    return _address(raw, "heap_base", recreate_dir,
                    "68000 code reads words from the Malloc block it is handed")


def _heap_limit(raw, recreate_dir):
    """The optional ``heap_limit`` address — the first address the arena may NOT reach — or None.

    ``heap_base`` says where the arena starts; this says where it must stop. Absent means the kit's
    own ceiling, the resolved ``emu.OS_FS_TABLE`` (``emu`` resolves the two, as it does for the
    base). A project sets it when the free window above its program is narrower than that — because
    its own scratch map, or a region its cases poke, sits below the table.

    Only the shape is checked here: whether the value leaves the arena any room at all is
    ``harness._vet_os_memory_map``'s question, since only it knows where the base ended up.
    """
    return _address(raw, "heap_limit", recreate_dir,
                    "it is a ceiling on the same arena, whose blocks are even addresses")


def _fs_base(raw, recreate_dir):
    """The optional ``fs_base`` address — the staged-file TABLE's base — or None when absent.

    The staging area follows a fixed ``os_map.OS_FS_STAGING_OFFSET`` above it, so this one key
    places the whole window; the mechanism is in ../README.md, "The staged-file window is the second
    region a project places". A project sets it when the window's default place leaves too little
    room below the stack guard for the files its boot opens — Flying Shark's opens eight totalling
    288,551 bytes, which the default 258,048-byte window cannot hold.

    None rather than the default itself, for ``_heap_base``'s reason: the default is C's
    (``OS_FS_TABLE_DEFAULT``, mirrored in ``os_map``), and ``emu`` resolves the two.

    Only the shape is checked here; whether the address is a legal PLACE — clear of the program, of
    the poked-input block and of the stack guard — is ``harness._vet_os_memory_map``'s question,
    because only it knows where the program ends. Odd is refused because every field of a table entry
    is a longword the model reads and writes through ``wr32``/``be32``, and 68000 code handed a
    staged file's address takes words from it.
    """
    return _address(raw, "fs_base", recreate_dir,
                    "every field of a table entry is a longword, and 68000 code reads words out of "
                    "the bytes the window serves")


def _program_data_ranges(raw, recreate_dir, poked_input_unused):
    """``poked_input_program_data`` as a tuple of ``(lo, hi)`` half-open ranges; empty when absent.

    Each entry is ``[address, length]`` naming bytes inside the harness-poked input block that are
    THIS PROGRAM's own data — a game variable that happens to share an address with the model's
    state. Declaring one lets ``harness.make_image`` seed it; it does not let a trap serve it, which
    ``emu._vet_no_poked_input_read`` still refuses on every run.

    Every shape is checked rather than interpreted, for ``_bool_flag``'s reason: this relaxes a
    safety check, and a malformed entry that silently declared the wrong span would let a poke land
    on the model's own state with nothing to say so. A range outside the block is refused too — the
    guard it relaxes only ever fires inside the block, so such an entry means the author has the
    wrong address rather than a wider permission.
    """
    key = "poked_input_program_data"
    if key not in raw:
        return ()
    if not poked_input_unused:
        raise ValueError(f"{recreate_dir / CONFIG_NAME}: `{key}` declares bytes inside the "
                         f"harness-poked input block, which is only a question at all for a project "
                         f"whose program covers that block — and such a project must set "
                         f"`tos_poked_input_unused`. Set it, with its evidence, or drop this.")
    ranges = []
    for entry in raw[key]:
        if not (isinstance(entry, list) and len(entry) == 2
                and all(isinstance(field, int) and not isinstance(field, bool) for field in entry)):
            raise TypeError(f"{recreate_dir / CONFIG_NAME}: every `{key}` entry is "
                            f"[address, length], two integers — not {entry!r}")
        address, length = entry
        if length <= 0:
            raise ValueError(f"{recreate_dir / CONFIG_NAME}: `{key}` entry at {address:#x} has "
                             f"length {length}; a range declares bytes, so it must be positive")
        if not (os_map.OS_CON_PENDING <= address
                and address + length <= os_map.OS_POKE_BLOCK_END):
            raise ValueError(
                f"{recreate_dir / CONFIG_NAME}: `{key}` entry [{address:#x}, {length}] is not "
                f"inside the poked-input block ({os_map.OS_CON_PENDING:#x}.."
                f"{os_map.OS_POKE_BLOCK_END - 1:#x}). It would relax nothing — that block is the "
                f"only place the guard fires — so the address is wrong.")
        fields = os_map.poked_input_fields_touched(address, length)
        if len(fields) > 1:
            raise ValueError(
                f"{recreate_dir / CONFIG_NAME}: `{key}` entry [{address:#x}, {length}] spans "
                f"{len(fields)} of the model's own fields ({', '.join(fields)}). A declaration says "
                f"'these bytes are MY program's data, not the model's', and that is a claim about "
                f"ONE variable — a span covering several is almost always a whole-block waiver "
                f"written as a range, which gives up every trap's staging area at once and can "
                f"never be justified byte by byte. Declare one field's worth at a time.")
        for lo, hi in ranges:
            if address < hi and lo < address + length:
                raise ValueError(
                    f"{recreate_dir / CONFIG_NAME}: `{key}` entry [{address:#x}, {length}] overlaps "
                    f"the earlier [{lo:#x}, {hi - lo}]. Two declarations of one byte are two claims "
                    f"about it, and nothing here can say which was meant — merge them.")
        ranges.append((address, address + length))
    return tuple(ranges)


def _rom_binding(raw, recreate_dir):
    """The optional ROM binding — ``(rom, rom_base, snapshot, stack_top)`` — or four Nones.

    A ROM project has no ``.PRG``: its image is a post-boot RAM SNAPSHOT with the ROM mapped over
    it at its real address, and the functions under test run in place up at ``rom_base`` (see
    ../README.md, "ROM mode"). The four keys arrive together because none of them means anything
    alone, and the harness's whole mode selection keys on their presence — so a project that names
    one and forgets another would silently be bound as a .PRG project with a missing file.
    """
    keys = ("rom", "rom_base", "snapshot", "stack_top")
    present = [key for key in keys if key in raw]
    if not present:
        return None, None, None, None
    missing = [key for key in keys if key not in raw]
    if missing:
        raise ValueError(f"{recreate_dir / CONFIG_NAME}: the ROM binding names {present} but not "
                         f"{missing}. All four are one declaration — the ROM image, where it is "
                         f"mapped, the post-boot RAM snapshot it runs over, and where the run's "
                         f"stack goes inside that RAM — and a partial one would bind this project "
                         f"as an ordinary .PRG project instead.")
    if "prg" in raw:
        raise ValueError(f"{recreate_dir / CONFIG_NAME}: a ROM project has no `prg`. Its image is "
                         f"the `snapshot` with the `rom` mapped over it; a .PRG named here would "
                         f"be silently ignored.")
    return ((recreate_dir / raw["rom"]).resolve(),
            _address(raw, "rom_base", recreate_dir,
                     "the ROM is mapped there and its code is fetched from it"),
            (recreate_dir / raw["snapshot"]).resolve(),
            _address(raw, "stack_top", recreate_dir,
                     "a 68000 pushes longwords onto A7, which an odd stack could not hold"))


# What a missing ROM-binding file means, and what to do about it. Neither is in the repository: the
# ROM is the machine's own (Atari's copyright, gitignored) and the snapshot is a build product
# captured from it — so "it is not there" is an ordinary state, not a corrupt checkout.
_ROM_FILE_REMEDIES = {"rom": "the ROM image is the machine's own and is gitignored",
                      "snapshot": "capture it with `make snapshot` in the project directory"}


def _vet_rom_files_exist(cfg):
    """Refuse a ROM binding whose ROM or snapshot is absent, naming the command that makes it.

    Both are read at IMPORT — ``emu`` sizes the memory map from their lengths before any test runs —
    so an absent one would otherwise surface as a bare ``FileNotFoundError`` from inside a ctypes
    install, naming neither the key nor the way to fix it.
    """
    for key, remedy in _ROM_FILE_REMEDIES.items():
        path = getattr(cfg, key)
        if not path.exists():
            raise FileNotFoundError(f"{cfg.dir / CONFIG_NAME} binds `{key}` to {path}, which does "
                                    f"not exist — {remedy}")


def load(recreate_dir):
    """Read ``<recreate_dir>/project.toml`` and bind it to the kit. Idempotent.

    Returns the config namespace: name, dir, prg, names, lib (absolute paths) plus
    load_base / image_size, the optional heap_base / heap_limit / fs_base, and the optional
    tos_malloc_unused / tos_xbios_video_unmodeled waivers (see harness's _vet_os_memory_map and
    _vet_os_event_state). Re-binding the kit to a *different* project inside one process is refused
    — the module-level constants derived here are already frozen.

    A ROM PROJECT'S NAMESPACE DIFFERS IN THREE PLACES (see _rom_binding and ../README.md, "ROM
    mode"): ``rom`` / ``rom_base`` / ``snapshot`` / ``stack_top`` are set rather than None, ``prg``
    is **None** — its image is the snapshot with the ROM mapped over it, so there is no program —
    and ``load_base`` is 0, which is where that image starts rather than a stand-in for a key the
    file does not carry. ``cfg.rom is not None`` is the one test for which kind of project it is.
    """
    global _CONFIG
    recreate_dir = Path(recreate_dir).resolve()
    if _CONFIG is not None:
        if _CONFIG.dir != recreate_dir:
            raise RuntimeError(f"recreate_kit is already bound to {_CONFIG.dir}; "
                               f"cannot rebind it to {recreate_dir} in the same process")
        return _CONFIG

    with open(recreate_dir / CONFIG_NAME, "rb") as fh:
        raw = tomllib.load(fh)
    poked_input_unused = _bool_flag(raw, "tos_poked_input_unused", recreate_dir)
    rom, rom_base, snapshot, stack_top = _rom_binding(raw, recreate_dir)
    cfg = SimpleNamespace(
        name=raw["name"],
        dir=recreate_dir,
        prg=None if rom else (recreate_dir / raw["prg"]).resolve(),
        # The ROM binding: all four or none (see _rom_binding). `rom` is the truth test every other
        # part of the kit asks — "is this project a ROM project?" — so it is the one that must not
        # be settable on its own.
        rom=rom,
        rom_base=rom_base,
        snapshot=snapshot,
        stack_top=stack_top,
        names=(recreate_dir / raw["names"]).resolve(),
        lib=(recreate_dir / raw["lib"]).resolve(),
        # Where the program is loaded. A ROM project has none, and its image starts at address 0 —
        # the machine's own RAM — so 0 is not a default standing in for a missing key but the
        # project's real base.
        load_base=0 if rom else raw["load_base"],
        image_size=raw["image_size"],
        # Optional: where the modeled Malloc arena starts, for a project whose program covers the
        # kit's default. None = that default; emu.OS_HEAP_BASE is the resolved value, installed into
        # both .so files at import and vetted by harness._vet_os_memory_map.
        heap_base=_heap_base(raw, recreate_dir),
        # Optional: the first address the arena may not reach, for a project whose free window ends
        # below the kit's own ceiling (emu.OS_FS_TABLE). None = that ceiling; emu.HEAP_LIMIT is
        # the resolved value, and emu.run() refuses any run that grew the bump pointer past it.
        heap_limit=_heap_limit(raw, recreate_dir),
        # Optional: where the staged-file window starts — the table, with its staging area a fixed
        # distance above it. None = the kit's own default; emu.OS_FS_TABLE / emu.OS_FS_STAGING are
        # the resolved addresses, installed into both .so files at import and vetted by
        # harness._vet_os_memory_map. A project sets it when the default window is too small for the
        # files its boot opens.
        fs_base=_fs_base(raw, recreate_dir),
        # Optional: the game issues no GEMDOS Malloc, so the modeled heap is never allocated from
        # and may sit inside its program. The project.toml declaring it must justify it there.
        tos_malloc_unused=_bool_flag(raw, "tos_malloc_unused", recreate_dir),
        # Optional: the game reads none of the harness-poked input state (no console call, no
        # Random, no Giaccess, no Kbdvbase), so the poked block may sit inside its program — which
        # a load_base below OS_POKE_BLOCK_END forces. See harness._vet_os_memory_map. The claim is
        # then enforced from both directions rather than trusted: harness.make_image refuses any
        # poke landing in the block, and emu._vet_no_poked_input_read refuses any run in which the
        # game's own code reads it.
        tos_poked_input_unused=poked_input_unused,
        # Optional, and only meaningful under the waiver above: the spans inside that block which
        # are the PROGRAM's OWN DATA rather than the model's. See _program_data_ranges.
        poked_input_program_data=_program_data_ranges(raw, recreate_dir, poked_input_unused),
        # Optional: this game's cores model the XBIOS video and colour group (Setscreen, Setpalette,
        # Setcolor, Vsync) as their OWN no-ops rather than through the kit's `os_setscreen` /
        # `os_setpalette` / `os_setcolor` / `os_vsync` doors, so the oracle records those events and
        # the candidate cannot. The waiver drops the four kinds from BOTH streams before they are
        # compared (harness._vet_os_event_state) — which is exactly the coverage every project had
        # before the doors existed, declared instead of assumed. Dropping it is a reconstruction
        # pass, not a config change: every one of that project's call sites has to route through the
        # door before the stream can match.
        tos_xbios_video_unmodeled=_bool_flag(raw, "tos_xbios_video_unmodeled", recreate_dir),
    )
    if cfg.rom is not None:
        _vet_rom_files_exist(cfg)

    if str(ORACLE) not in sys.path:
        sys.path.insert(0, str(ORACLE))
    import loader                                   # noqa: E402  (only importable after the path insert)
    loader.LOAD_BASE = cfg.load_base
    loader.IMAGE_SIZE = cfg.image_size

    _CONFIG = cfg
    return cfg


def current():
    """The bound config, or a loud error if no project has been bound yet."""
    if _CONFIG is None:
        raise RuntimeError("no project bound — call recreate_kit.project.load(<recreate dir>) "
                           "before importing the kit's oracle/harness modules")
    return _CONFIG
