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
from `projects/bubbleghost/recreate/test/test_constants.py` (originally Joust's).

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

import pytest

import abi
import emu
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


@functools.lru_cache(maxsize=None)
def defines(path):
    """{name: value} for every define `_DEFINE_RE` can read in one of this project's files.

    Public, and the ONLY reader of a header in this suite — `test_image_model.py` pins its mirrors
    with it and the three sweeps below walk the tree with it.

    Memoised: every mirror of every battery re-reads and re-scans its header, which on the sibling
    projects' scale was measured at 55 reads of the same file in one run.

    Out of reach on purpose: a value built from other macros or from arithmetic. Evaluating those
    would mean resolving one header's macros against another's, which is a C preprocessor and not a
    scraper; a battery that mirrors such a value pins the derivation in its own test instead. So is
    a name defined TWICE in ONE file, which this collapses to the last: that one the compiler
    diagnoses itself, as a macro redefinition, and `test_no_constant_is_defined_in_two_files` is
    about the copy in another file that no translation unit ever sees beside the first.
    """
    return {m["name"]: (int(m["literal"], 0) if m["literal"] else 1 << int(m["bit"]))
            for m in _DEFINE_RE.finditer((REC / path).read_text())}


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

    NO CORES AT ALL IS A SKIP, and a loud one, on the same argument as
    `test_status.py::test_every_named_function_is_verified_or_deferred`: while `src/` holds no `.c`
    the three gates below iterate an empty list and PASS, which reads exactly like "every battery
    declares its pins" and is the state this project bootstraps in. `test_image_model.py` is what
    carries the pins meanwhile, and it declares them in the same shape.
    """
    stems = sorted(path.stem for path in (REC / "src").glob("*.c"))
    if not stems:
        pytest.skip("no src/*.c yet, so there is no battery to check — this gate arms with the "
                    "first core anyone ports (README.md, 'Adding a function', step 4)")
    missing = [stem for stem in stems if not (TEST_DIR / f"test_{stem}.py").exists()]
    assert not missing, (
        "these reconstruction sources have no differential battery beside them: "
        + ", ".join(f"src/{stem}.c wants test/test_{stem}.py" for stem in missing)
        + " — every core is verified against the original by a battery of its own (README.md, "
          "'Adding a function'), and a core with none is unverified rather than exempt")
    return [(stem, importlib.import_module(f"test_{stem}")) for stem in stems]


# The header a bare `MIRRORS` name is looked up in. A battery that mirrors its own subsystem's
# header says so by setting `MIRROR_HEADER` at the top of its file; everything else mirrors the
# memory model.
DEFAULT_MIRROR_HEADER = "include/globals.h"


def _mirror_rows(module):
    """`module.MIRRORS`' rows as (python_name, c_path, c_name), whichever way they are written.

    A row is normally just the NAME, spelt the same on both sides and read out of the module's
    `MIRROR_HEADER` — which is the overwhelmingly common case, and a row that said the one name
    three times carried no information while hiding the rows that do. The (name, path, name) triple
    stays available for the row that really differs: a constant borrowed from another subsystem's
    header, or one this side deliberately spells differently.
    """
    header = getattr(module, "MIRROR_HEADER", DEFAULT_MIRROR_HEADER)
    for row in module.MIRRORS:
        yield (row, header, row) if isinstance(row, str) else row


def check_mirrors(module):
    """Assert every row in `module.MIRRORS` equals the C define it names.

    Shared with `test_image_model.py`, which declares the same two names and checks them itself —
    it is not a battery (there is no `src/image_model.c`) but the memory model still has to be
    pinned before any battery exists. The loop lived in both files until one of them was edited.
    """
    for python_name, c_path, c_name in _mirror_rows(module):
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

    THE RANGE TEST IS THE DEFINITION, not a convenience: a `<prefix>*` name holding something that
    is not a program address cannot be pinned against bytes at all, so it is not required to be. The
    rule earns its keep the moment a battery names a GEOMETRY constant with an `ENTRY_` prefix —
    `projects/bubbleghost/recreate/test/test_gameplay.py`'s `ENTRY_POINT_PIXELS`, the tile size an
    entry point is scaled by, is the sibling's case. Everything that IS an address must be pinned,
    and `check_entry_prologues` names any that is not.
    """
    return {name: value for name, value in vars(module).items()
            if name.startswith(prefix) and isinstance(value, int)
            and loader.LOAD_BASE <= value < loader.PROGRAM_END}


def check_entry_prologues(module):
    """Every `ENTRY_*` and `STOP_*` a battery declares still points at the bytes it names.

    Pinned against the ORIGINAL'S OWN BYTES rather than against a name file, so the check needs
    nothing but the .PRG the harness already loaded — which matters here, where `../names.txt` is
    still being written. Around eight bytes is the working length: this program is hand-written
    assembly whose routines mostly open `movem.l #$fffe,-(a7)` or a `lea` of an absolute long, so a
    two-byte pin would match dozens of them. Each row spells whole instructions, and how many is the
    row's own business.

    EVERY DECLARED ADDRESS MUST BE PINNED, and an unpinned one fails BY NAME. A dict of pins can only
    ever check what is in it, so a battery that adds an entry and forgets its row gets no check at
    all and no complaint — in `projects/bubbleghost/recreate`, where this came from, that is how
    `ENTRY_SAVE_HISCORES` and eleven `STOP_*` went unpinned until the rule was added. A STOP_ is
    pinned exactly as an ENTRY_ is, and it is worth as much: a checkpoint one instruction early diffs
    a routine before its last store and comes back clean.

    `harness.BASE_IMAGE` is the .PRG AS LOADED, deliberately: an entry address is a fact about the
    binary, not about the post-load image `conftest.py` stages every case on. The two agree over
    every OPCODE anyway: the boot chain writes the bss, the data segment and the vector page, and the
    one thing it stores into TEXT is the `jmp` OPERAND at 0x11650 (`conftest.A_vbl_chain_vector`),
    which is a longword of data that happens to live there.
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
    reason that mattered: it stayed green while any ONE battery still declared a pin. It SKIPS while
    no function is ported, which is the state this project bootstraps in, rather than passing over an
    empty list — `_batteries()` is where that arm lives.
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
        for name in defines(path):
            homes.setdefault(name, []).append(path)
    duplicated = {name: paths for name, paths in homes.items() if len(paths) > 1}
    assert not duplicated, "constants defined in more than one file: " + "; ".join(
        f"{name} in {', '.join(paths)}" for name, paths in sorted(duplicated.items()))


def test_no_address_has_two_spellings():
    """One ADDRESS, one name. `A_*` is this reconstruction's spelling for an absolute Ghidra
    address, and one address is one global — so a second `A_*` name for the same number is a second
    spelling of one variable, which is how a subsystem ends up editing state it does not own.

    Only the `A_*` family is checked, and deliberately so: for record offsets and geometry a shared
    value carries no information (`SPRITE_RECORD_DATA` and a future `ENTITY_X` are both 0 and both
    right). This game reaches every global as an absolute long, so the same number really does
    appear in two subsystems' `lea`s and the two agents reading them have no way to see each
    other's line.
    """
    names = {}
    for path in _sources():
        for name, value in defines(path).items():
            if name.startswith("A_"):
                names.setdefault(value, set()).add(name)
    clashes = {value: sorted(n) for value, n in names.items() if len(n) > 1}
    assert not clashes, "one address under two names: " + "; ".join(
        f"{value:#x} is {' and '.join(n)}" for value, n in sorted(clashes.items()))


def test_every_named_address_is_inside_the_program():
    """An `A_*` that is not a game address at all — a table offset written where an address belongs.

    Every global this program has lies in its TEXT, DATA or BSS: it is hand-written assembly with
    absolute long addressing throughout, so a `var` line in `../names.txt` is always somewhere in
    [load_base, PROGRAM_END). The screen ring is the ONE region of live game memory outside that
    window, and it is deliberately not an `A_*`: its address is computed from Physbase at run time,
    the harness only chooses where (`test/abi.py`), and a core must read `A_screen_ring_base` out of
    the image rather than compile a constant in.
    """
    for path in _sources():
        for name, value in defines(path).items():
            if name.startswith("A_"):
                assert loader.LOAD_BASE <= value < loader.PROGRAM_END, (
                    f"{path}'s {name} = {value:#x} is outside the program "
                    f"[{loader.LOAD_BASE:#x}, {loader.PROGRAM_END:#x}) — if it names the screen "
                    f"ring, that address is chosen by test/abi.py and is not an `A_*`")


def test_the_scratch_map_is_clear_of_the_program_the_ring_and_the_file_table():
    """`test/abi.py` parks its stub and buffers in "free" image space — this is what makes it free.

    Two hazards, and the second is the one specific to this game: above the program is not enough,
    because the harness itself places a 0x27600-byte screen ring above the program (`abi.py`,
    "where the harness puts the screen ring"), which the game overwrites every frame. A stub or a
    scratch buffer parked there would be a false green today and a baffling failure the day the
    first draw routine lands. The ring's own clearance is `test_image_model.py`'s.
    """
    ring_lo, ring_hi = abi.SCREEN_RING_SPAN
    top = abi.SCRATCH + abi.SCRATCH_BYTES
    for name in ("STUB", "RESULT", "SCRATCH"):
        base = getattr(abi, name)
        assert base >= loader.PROGRAM_END, (
            f"abi.{name} {base:#x} is inside the program, which ends at {loader.PROGRAM_END:#x}")
        assert not (base < ring_hi and ring_lo < base + abi.SCRATCH_BYTES), (
            f"abi.{name} {base:#x} overlaps the screen ring [{ring_lo:#x}, {ring_hi:#x})")
    assert abi.STUB < abi.RESULT < abi.SCRATCH, "the map's three regions are in address order"
    assert top <= harness.OS_FS_TABLE, (
        f"the scratch map reaches {top:#x}, at or past the TOS model's staged-file table "
        f"{harness.OS_FS_TABLE:#x}")


def test_the_register_call_stub_assembles_and_runs():
    """`abi.register_call_pokes` is a hand-assembled encoding, so it is run rather than read.

    It has no caller yet — this project's first differential battery is what will give it one — and
    an unassembled encoding that no case executes is exactly the kind of head start that is wrong
    the first time it is used. So: call a poked `rts`, store two registers, and check both landed
    where the docstring says, in the order it says.
    """
    routine = abi.SCRATCH
    image = harness.make_image({routine: b"\x4e\x75", **abi.register_call_pokes(routine, ("d0", "a1"))})
    d0, a1 = 0x11223344, 0x55667788
    final, _writes, _regs = emu.run(image, abi.STUB, regs={"a0": abi.RESULT, "d0": d0, "a1": a1})
    stored = [int.from_bytes(final[abi.RESULT + 4 * i:abi.RESULT + 4 * i + 4], "big")
              for i in range(2)]
    assert stored == [d0, a1]
