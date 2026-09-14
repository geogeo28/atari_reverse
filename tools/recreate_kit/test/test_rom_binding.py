"""`project._rom_binding()` decides whether a project is bound as a ROM or as a .PRG.

Everything ROM mode changes hangs off that one answer — the image the harness builds, the memory map
the oracle installs, whether the TOS trap model is in the picture at all — so a partial or malformed
binding must not be interpreted. The four keys are one declaration: a project that names `rom` and
forgets `snapshot` would otherwise be bound as an ordinary .PRG project with a missing file, and the
error would name the file rather than the mistake.

No project binding is needed: the helper is pure, so it is tested directly on a dict.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # reverse/tools, so `recreate_kit` imports
from recreate_kit import project   # noqa: E402  (only importable after the path insert)

RECREATE_DIR = Path("/nowhere/projects/example/recreate")   # only ever joined with, never read

ROM_KEYS = ("rom", "rom_base", "snapshot", "stack_top")
COMPLETE = {"rom": "../../../tools/hatari/TOS102US.img", "rom_base": 0xFC0000,
            "snapshot": "build/boot_ram.bin", "stack_top": 0x80000}


def test_no_rom_key_binds_a_prg_project():
    assert project._rom_binding({"prg": "game.prg"}, RECREATE_DIR) == (None, None, None, None)


def test_a_complete_binding_resolves_its_paths_and_addresses():
    rom, rom_base, snapshot, stack_top = project._rom_binding(dict(COMPLETE), RECREATE_DIR)
    assert rom == (RECREATE_DIR / COMPLETE["rom"]).resolve()
    assert snapshot == (RECREATE_DIR / COMPLETE["snapshot"]).resolve()
    assert (rom_base, stack_top) == (COMPLETE["rom_base"], COMPLETE["stack_top"])


@pytest.mark.parametrize("missing", ROM_KEYS)
def test_a_partial_binding_is_refused_by_name(missing):
    """The one that matters: three keys out of four is a project that would bind as a .PRG."""
    raw = {key: value for key, value in COMPLETE.items() if key != missing}
    # A WORD-BOUNDED match, because `match=` is a substring search: the message also lists the keys
    # that ARE present, so a bare "rom" would match the `'rom_base'` in that list and the case would
    # pass on a message that never named the missing key — which is the one thing it pins.
    with pytest.raises(ValueError, match=rf"\b{missing}\b"):
        project._rom_binding(raw, RECREATE_DIR)


def test_a_rom_project_may_not_also_name_a_prg():
    """Its image is the snapshot with the ROM over it; a `prg` here would be silently ignored."""
    with pytest.raises(ValueError, match="prg"):
        project._rom_binding({**COMPLETE, "prg": "game.prg"}, RECREATE_DIR)


@pytest.mark.parametrize("key", ("rom_base", "stack_top"))
@pytest.mark.parametrize("value", (0xFC0001, 0, -0x10000, "0xfc0000", True))
def test_an_address_that_is_not_a_positive_even_integer_is_refused(key, value):
    """A 68000 fetches instructions and longwords on word boundaries only, and a quoted address is
    the hand-edit that would otherwise reach `int()`-less arithmetic much later."""
    with pytest.raises((TypeError, ValueError), match=key):
        project._rom_binding({**COMPLETE, key: value}, RECREATE_DIR)
