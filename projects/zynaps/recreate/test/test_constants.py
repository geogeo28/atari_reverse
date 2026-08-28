"""Pin every mirrored constant and entry address to its single source of truth, and refuse a value
or a name that is spelt in two of this project's headers.

The differential batteries restate values that really live somewhere else: record offsets, table
addresses and sprite geometry that belong to the C in `include/` and `src/`, and entry addresses
that belong to the binary. Python cannot import either, so CLAUDE.md's rule applies — pick one
canonical definition and pin the copy equal with a test. A drift on either side then fails with the
name of the constant, instead of quietly weakening a battery: flipping `ENTITY_ALIVE` in
`include/entity.h` would otherwise leave `test_entity.py` poking the old offset and still passing,
on both sides, having tested nothing.

THE DUPLICATE PINS BELOW EXIST BECAUSE OF THE PER-SUBSYSTEM HEADER SPLIT. Each subsystem owns its
own header, and a subsystem that needs another's global includes that header rather than restating
the address. Nothing in C would diagnose a second copy — no translation unit includes every header,
so two spellings of one address never meet the compiler. These two tests are that diagnosis, ported
from `projects/joust/recreate/test/test_constants.py`.

THIS FILE IS A COLLECTOR, NOT A REGISTRY, and that is deliberate: several agents add functions to
this project at once, so a central list here would be the one place all of them had to edit. Each
`test_<subsystem>.py` declares its own `MIRRORS` and `ENTRY_PROLOGUES` at the bottom of the file and
this module discovers them. See README.md, "Adding a function".
"""
import importlib
import re
from pathlib import Path

import abi
import harness

import loader

REC = Path(__file__).resolve().parents[1]

# Two spellings of a constant value: an integer literal, and the single-bit shift a flag-bit macro
# uses. The trailing lookahead makes the value the WHOLE definition, so a compound expression that
# merely starts with one of these forms — `(1u << 6) | (1u << 11)`, `0x10 + BAR` — stays invisible
# rather than being half-read into a plausible wrong number. Include guards have no value at all and
# never match either branch.
_DEFINE_RE = re.compile(r"^#define\s+(?P<name>\w+)\s+(?:"
                        r"(?P<literal>0[xX][0-9a-fA-F]+|\d+)[uU]?"
                        r"|\(\s*1[uU]?\s*<<\s*(?P<bit>\d+)\s*\)"
                        r")(?=\s*(?:/[/*]|$))", re.M)


def _iter_defines(path):
    """(name, value) for every define `_DEFINE_RE` can read in one of this project's files."""
    for m in _DEFINE_RE.finditer((REC / path).read_text()):
        yield m["name"], (int(m["literal"], 0) if m["literal"] else 1 << int(m["bit"]))


def _defines(path):
    """{name: value} for the same.

    Out of reach on purpose: a value built from other macros or from arithmetic. Evaluating those
    would mean resolving one header's macros against another's, which is a C preprocessor and not a
    scraper; a battery that mirrors such a value pins the derivation in its own test instead.
    """
    return dict(_iter_defines(path))


def _sources():
    """This reconstruction's headers and translation units, relative to its root.

    Globbed, not enumerated, so a file another agent adds is covered the moment it exists. Not the
    kit's own headers, which every TU also compiles against — those are the kit's to keep coherent.
    """
    return [str(path.relative_to(REC))
            for path in sorted(list((REC / "include").glob("*.h")) + list((REC / "src").glob("*.c")))]


def _batteries():
    """Every differential battery: a `test_<stem>.py` for which `src/<stem>.c` exists.

    Keyed on the source file rather than on a name list so that a subsystem another agent adds is
    required to declare its pins from the moment its first function lands — and so that this
    module's own helpers (test_status, test_heap_guard, this file) are not mistaken for batteries.
    """
    stems = {path.stem for path in (REC / "src").glob("*.c")}
    return [(stem, importlib.import_module(f"test_{stem}"))
            for stem in sorted(stems) if (Path(__file__).parent / f"test_{stem}.py").exists()]


def test_every_battery_declares_its_pins():
    """A battery with no MIRRORS/ENTRY_PROLOGUES is unpinned, and silence would look like coverage.

    This replaces a suite-global "something was checked" assertion, which could never fail for the
    reason that mattered: it stayed green while any ONE battery still declared a pin.
    """
    for stem, module in _batteries():
        assert getattr(module, "MIRRORS", None), (
            f"test_{stem}.py declares no MIRRORS — every battery restates at least the constants "
            f"its cases poke; declare them at the bottom of the file (see README.md)")
        assert getattr(module, "ENTRY_PROLOGUES", None), (
            f"test_{stem}.py declares no ENTRY_PROLOGUES — an entry address that is never pinned "
            f"could point at a different routine and still come back clean")


def test_mirrored_constants_match_the_c():
    """Every (python_name, c_path, c_name) triple a battery declares in its `MIRRORS`."""
    for stem, module in _batteries():
        for python_name, c_path, c_name in module.MIRRORS:
            c_value = _defines(c_path).get(c_name)
            assert c_value is not None, f"{c_path} no longer defines {c_name} (test_{stem}.py)"
            assert getattr(module, python_name) == c_value, (
                f"test_{stem}.py's {python_name} = {getattr(module, python_name):#x} but "
                f"{c_path}'s {c_name} = {c_value:#x}")


def test_entry_addresses_still_point_at_their_routines():
    """A mistyped entry would silently run a different routine — and could still come back clean.

    Each battery's `ENTRY_PROLOGUES` maps its `ENTRY_*` constant to the first bytes of the routine
    at that address, read off the loaded image when the entry was established. Pinned against the
    ORIGINAL'S OWN BYTES rather than against a name file, so the check needs nothing but the .PRG the
    harness already loaded. Ten bytes is the working length: the two preshift builders share their
    first eight (`clr.l d5 / move.w d2,d5 / lsl.l #3,d5 / sub.w d2,d5`) and separate only at byte 8,
    so a shorter prologue would not tell them apart.
    """
    for stem, module in _batteries():
        for python_name, prologue in module.ENTRY_PROLOGUES.items():
            entry = getattr(module, python_name)
            expected = bytes.fromhex(prologue)
            actual = bytes(harness.BASE_IMAGE[entry:entry + len(expected)])
            assert actual == expected, (
                f"test_{stem}.py's {python_name} = {entry:#x} holds {actual.hex()}, "
                f"not the {expected.hex()} this routine starts with")


def test_no_constant_is_defined_in_two_files():
    """One NAME, one home. A header split invites a second copy that no TU ever sees beside the
    first, so the compiler cannot catch it and only this can."""
    homes = {}
    for path in _sources():
        for name, _value in _iter_defines(path):
            homes.setdefault(name, []).append(path)
    duplicated = {name: paths for name, paths in homes.items() if len(paths) > 1}
    assert not duplicated, "constants defined in more than one file: " + "; ".join(
        f"{name} in {', '.join(paths)}" for name, paths in sorted(duplicated.items()))


def test_no_address_has_two_spellings():
    """One ADDRESS, one name. `A_*` is this reconstruction's spelling for an absolute Ghidra
    address, and one address is one global — so a second `A_*` name for the same number is a second
    spelling of one variable, which is how a subsystem ends up editing state it does not own.

    Only the `A_*` family is checked, and deliberately so: for record offsets and geometry a shared
    value carries no information (`ENTITY_X` and a future `SHOT_X` are both 0 and both right).
    """
    names = {}
    for path in _sources():
        for name, value in _iter_defines(path):
            if name.startswith("A_"):
                names.setdefault(value, set()).add(name)
    clashes = {value: sorted(n) for value, n in names.items() if len(n) > 1}
    assert not clashes, "one address under two names: " + "; ".join(
        f"{value:#x} is {' and '.join(n)}" for value, n in sorted(clashes.items()))


def test_scratch_map_is_clear_of_the_program_and_the_framebuffers():
    """test/abi.py parks its stub and buffers in "free" image space — this is what makes it free.

    Two hazards, and the second is the one that bit: above the program is not enough, because Zynaps
    hard-codes its framebuffers at absolute RAM rather than allocating them, so 63 KB in the middle
    of the free space belongs to the game. The scratch map used to start 0x300 bytes BELOW
    `screen_back`, which no case noticed only because no ported routine draws yet.
    """
    top = abi.SCRATCH + abi.SCRATCH_BYTES
    assert abi.STUB >= loader.PROGRAM_END, (
        f"abi.STUB {abi.STUB:#x} is inside the program, which ends at {loader.PROGRAM_END:#x}")
    screen_lo, screen_hi = abi.SCREEN_SPAN
    for name in ("STUB", "RESULT", "SCRATCH"):
        base = getattr(abi, name)
        assert base >= loader.PROGRAM_END, f"abi.{name} {base:#x} is inside the program"
        assert not (base < screen_hi and screen_lo < base + abi.SCRATCH_BYTES), (
            f"abi.{name} {base:#x} overlaps the game's framebuffers "
            f"[{screen_lo:#x}, {screen_hi:#x}) — see ../names.txt's screen_back / screen_front")
    assert top <= harness.OS_FS_TABLE, (
        f"the scratch map reaches {top:#x}, at or past the TOS model's staged-file table "
        f"{harness.OS_FS_TABLE:#x}")
