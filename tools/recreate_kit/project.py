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
