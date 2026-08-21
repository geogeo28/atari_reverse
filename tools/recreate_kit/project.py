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


def load(recreate_dir):
    """Read ``<recreate_dir>/project.toml`` and bind it to the kit. Idempotent.

    Returns the config namespace: name, dir, prg, names, lib (absolute paths) plus
    load_base / image_size and the optional tos_malloc_unused waiver (see harness's
    _vet_os_memory_map). Re-binding the kit to a *different* project inside one
    process is refused — the module-level constants derived here are already frozen.
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
    cfg = SimpleNamespace(
        name=raw["name"],
        dir=recreate_dir,
        prg=(recreate_dir / raw["prg"]).resolve(),
        names=(recreate_dir / raw["names"]).resolve(),
        lib=(recreate_dir / raw["lib"]).resolve(),
        load_base=raw["load_base"],
        image_size=raw["image_size"],
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
    )

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
