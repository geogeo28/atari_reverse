"""Pin every mirrored constant and entry address to its single source of truth, and refuse a value
or a name that is spelt in two of this project's headers.

The differential batteries restate values that really live somewhere else: record offsets, table
addresses and geometry that belong to the C in `include/` and `src/`, and entry addresses that
belong to the binary. Python cannot import either, so CLAUDE.md's rule applies — pick one canonical
definition and pin the copy equal with a test. A drift on either side then fails with the name of
the constant, instead of quietly weakening a battery: flipping an offset in a header would otherwise
leave its battery poking the old one and still passing, on both sides, having tested nothing.

THE DUPLICATE PINS BELOW EXIST BECAUSE OF THE PER-SUBSYSTEM HEADER SPLIT. Each subsystem owns its
own header, and a subsystem that needs another's global includes that header rather than restating
the address. Nothing in C would diagnose a second copy — no translation unit includes every header,
so two spellings of one address never meet the compiler. These two tests are that diagnosis, ported
from `projects/zynaps/recreate/test/test_constants.py` (originally Joust's).

THIS FILE IS A COLLECTOR, NOT A REGISTRY, and that is deliberate: several agents add functions to
this project at once, so a central list here would be the one place all of them had to edit. Each
`test_<subsystem>.py` declares its own `MIRRORS` and `ENTRY_PROLOGUES` at the bottom of the file and
this module discovers them, keyed on `src/<subsystem>.c` existing. See README.md, "Adding a
function".

`test_image_model.py` declares the same two names and checks them itself, because it is not a
battery — there is no `src/image_model.c` — and the memory model still has to be pinned before any
battery exists at all. It imports `defines()` from here rather than growing a second scraper.
"""
import functools
import importlib
import re
from pathlib import Path

import harness

import loader

REC = Path(__file__).resolve().parents[1]
TEST_DIR = Path(__file__).resolve().parent

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


@functools.lru_cache(maxsize=None)
def defines(path):
    """{name: value} for the same. Public — `test_image_model.py` pins its mirrors with it.

    Memoised: every mirror of every battery re-reads and re-scans its header, which on the sibling
    projects' scale was measured at 55 reads of the same file in one run.

    Out of reach on purpose: a value built from other macros or from arithmetic. Evaluating those
    would mean resolving one header's macros against another's, which is a C preprocessor and not a
    scraper; a battery that mirrors such a value pins the derivation in its own test instead.
    """
    return dict(_iter_defines(path))


@functools.lru_cache(maxsize=None)
def _sources():
    """This reconstruction's headers and translation units, relative to its root.

    Globbed, not enumerated, so a file another agent adds is covered the moment it exists. Not the
    kit's own headers, which every TU also compiles against — those are the kit's to keep coherent.

    Memoised for `defines`' reason: three cases below sweep the whole tree, and the glob is the
    same each time within one process.
    """
    return tuple(str(path.relative_to(REC))
                 for path in sorted(list((REC / "include").glob("*.h"))
                                    + list((REC / "src").glob("*.c"))))


def _batteries():
    """Every differential battery: the `test_<stem>.py` beside each `src/<stem>.c`.

    Keyed on the source file rather than on a name list so that a subsystem another agent adds is
    required to declare its pins from the moment its first function lands — and so that this
    module's own helpers (test_status, test_image_model, this file) are not mistaken for batteries.

    A CORE WITH NO BATTERY IS A FAILURE, not a skip. This used to drop such a stem quietly, so a
    `src/x.c` whose `test_x.py` was never written — or was renamed, or lost in a merge — left every
    check below passing over the files that remained: the unpinned subsystem was exactly the one
    nothing looked at, and the suite got QUIETER as it grew.
    """
    stems = sorted(path.stem for path in (REC / "src").glob("*.c"))
    missing = [stem for stem in stems if not (TEST_DIR / f"test_{stem}.py").exists()]
    assert not missing, (
        "these reconstruction sources have no differential battery beside them: "
        + ", ".join(f"src/{stem}.c wants test/test_{stem}.py" for stem in missing)
        + " — every core is verified against the original by a battery of its own (README.md, "
          "'Adding a function'), and a core with none is unverified rather than exempt")
    return [(stem, importlib.import_module(f"test_{stem}")) for stem in stems]


def check_mirrors(module):
    """Assert every (python_name, c_path, c_name) triple in `module.MIRRORS` equals the C define.

    Shared with `test_image_model.py`, which declares the same two names and checks them itself —
    it is not a battery (there is no `src/image_model.c`) but the memory model still has to be
    pinned before any battery exists. The loop lived in both files until one of them was edited.
    """
    for python_name, c_path, c_name in module.MIRRORS:
        c_value = defines(c_path).get(c_name)
        assert c_value is not None, f"{c_path} no longer defines {c_name} ({module.__name__}.py)"
        assert getattr(module, python_name) == c_value, (
            f"{module.__name__}.py's {python_name} = {getattr(module, python_name):#x} but "
            f"{c_path}'s {c_name} = {c_value:#x}")


# The two families of address constant a battery declares, and the dict that must pin each. An
# ENTRY_* is where a run starts; a STOP_* is the checkpoint PC it is diffed at (`stop_pc`). Both are
# addresses in the original, and both are equally able to point at the wrong instruction.
_ADDRESS_FAMILIES = (("ENTRY_", "ENTRY_PROLOGUES"), ("STOP_", "STOP_PROLOGUES"))


def _declared_addresses(module, prefix):
    """The module-level `<prefix>*` names whose value is an address inside the loaded program.

    THE RANGE TEST IS THE DEFINITION, not a convenience: a `<prefix>*` name holding something that is
    not a program address cannot be pinned against bytes at all, and this project has one —
    `test_gameplay.py`'s `ENTRY_POINT_PIXELS`, which is the tile size a bubble entry point is scaled
    by and mirrors `include/gameplay.h`. Everything that IS an address must be pinned, and the check
    below names any that is not.
    """
    return {name: value for name, value in vars(module).items()
            if name.startswith(prefix) and isinstance(value, int)
            and loader.LOAD_BASE <= value < loader.PROGRAM_END}


def check_entry_prologues(module):
    """Every `ENTRY_*` and `STOP_*` a battery declares still points at the bytes it names.

    Pinned against the ORIGINAL'S OWN BYTES rather than against a name file, so the check needs
    nothing but the .PRG the harness already loaded — which matters here, where `../names.txt` is
    still being written. Eight bytes is the working length: almost every function in this program
    opens `link a6,#-n`, so a shorter prologue would tell none of them apart.

    EVERY DECLARED ADDRESS MUST BE PINNED, and an unpinned one fails BY NAME. A dict of pins can only
    ever check what is in it, so a battery that adds an entry and forgets its row gets no check at
    all and no complaint — which is how `ENTRY_SAVE_HISCORES` and eleven `STOP_*` went unpinned here.
    A STOP_ is pinned exactly as an ENTRY_ is, and it is worth as much: a checkpoint one instruction
    early diffs a routine before its last store and comes back clean.

    `harness.BASE_IMAGE` is the .PRG AS LOADED, deliberately: an entry address is a fact about the
    binary, not about the post-init image `conftest.py` stages every case on, and the two agree over
    TEXT anyway (`init_globals` writes only the bss).
    """
    for prefix, dict_name in _ADDRESS_FAMILIES:
        declared = _declared_addresses(module, prefix)
        pins = getattr(module, dict_name, {})
        missing = sorted(set(declared) - set(pins))
        assert not missing, (
            f"{module.__name__}.py declares {', '.join(missing)} but pins "
            f"{'them' if len(missing) > 1 else 'it'} in no {dict_name} row — an address that is "
            f"never pinned could point at a different instruction and still come back clean")
        unknown = sorted(set(pins) - set(declared))
        assert not unknown, (
            f"{module.__name__}.py's {dict_name} pins {', '.join(unknown)}, which is not a "
            f"module-level {prefix}* address — a row that names nothing checks nothing")
        for python_name, prologue in pins.items():
            entry = declared[python_name]
            expected = bytes.fromhex(prologue)
            actual = bytes(harness.BASE_IMAGE[entry:entry + len(expected)])
            assert actual == expected, (
                f"{module.__name__}.py's {python_name} = {entry:#x} holds {actual.hex()}, "
                f"not the {expected.hex()} this address holds")


def test_every_battery_declares_its_pins():
    """A battery with no MIRRORS/ENTRY_PROLOGUES is unpinned, and silence would look like coverage.

    This replaces a suite-global "something was checked" assertion, which could never fail for the
    reason that mattered: it stayed green while any ONE battery still declared a pin. Vacuous while
    no function is ported, which is the state this project bootstraps in — `test_image_model.py` is
    what carries the pins meanwhile, and it declares them in the same shape.
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
    for _stem, module in _batteries():
        check_mirrors(module)


def test_entry_addresses_still_point_at_their_routines():
    """A mistyped entry would silently run a different routine — and could still come back clean.

    Also fails, by name, on an `ENTRY_*` or `STOP_*` a battery declares and never pins."""
    for _stem, module in _batteries():
        check_entry_prologues(module)


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
    value carries no information. It matters more here than in a hand-assembled game: a global is
    reached as `n(a4)`, so two subsystems that meet the same variable through different call paths
    write down the same `A4_BASE + n` under two names without ever seeing each other's line.
    """
    names = {}
    for path in _sources():
        for name, value in _iter_defines(path):
            if name.startswith("A_"):
                names.setdefault(value, set()).add(name)
    clashes = {value: sorted(n) for value, n in names.items() if len(n) > 1}
    assert not clashes, "one address under two names: " + "; ".join(
        f"{value:#x} is {' and '.join(n)}" for value, n in sorted(clashes.items()))


def test_every_named_address_is_inside_the_program():
    """An `A_*` that is not a game address at all — a displacement written where an address belongs.

    The `n(a4)` model makes this the easy mistake in this project: `-7212(a4)` is a global, and
    `#define A_screen_state 7212` is a plausible-looking line that names nothing. Every real global
    lies in the BSS or the DATA above it, so the window is [BG_BSS_BASE, PROGRAM_END).
    """
    bss_base = defines("include/globals.h")["BG_BSS_BASE"]
    for path in _sources():
        for name, value in _iter_defines(path):
            if name.startswith("A_"):
                assert bss_base <= value < loader.PROGRAM_END, (
                    f"{path}'s {name} = {value:#x} is outside the program's globals "
                    f"[{bss_base:#x}, {loader.PROGRAM_END:#x}) — an `n(a4)` displacement is not an "
                    f"address; the address is A4_BASE + n, signed")
