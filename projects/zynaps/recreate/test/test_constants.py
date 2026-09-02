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
import subprocess
from pathlib import Path

import pytest

import abi
import harness

import loader
from recreate_kit import asm_twin

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


# ---- the asm twins' own constants ---------------------------------------------------------------
# `src/asm/` cannot include `include/*.h`: those headers spell their values with C's `u` suffix,
# which the assembler will not parse. So each twin restates the handful it needs as `.equ`, and
# CLAUDE.md's rule for two spellings that cannot import each other applies — pin the copy equal with
# a test. This is that test, and it reads the values out of the ASSEMBLED OBJECT rather than out of
# the `.S` text: what it compares is then the number the assembler actually used, arithmetic and all,
# rather than a second parse of the source that could read `SCROLL_PHASE_STEP * 2` as anything.
#
# PER OBJECT, NOT PER BLOB, and that is the difference between a pin and a decoration. Three `.S`
# files declare `SCREEN_ROW_BYTES` and two declare `A_scroll_prefill_hide_screen`; in the LINKED blob
# those collapse to one symbol, so a wrong value in one file was covered by its neighbour's correct
# one and this test passed (measured: `.equ SCREEN_ROW_BYTES, 168` in scroll_blit.S alone went
# green). kit.mk keeps `build/asm/<stem>.o` per source for exactly this.
_EQU_RE = re.compile(r'^\s*\.equ\s+(\w+)\s*,', re.M)
# Any `#define NAME`, whatever its value looks like — the set of names a header OWNS, as opposed to
# `_iter_defines`'s narrower set of names whose value it can also read. The gap between the two is
# where an unpinned constant used to hide.
_DEFINE_NAME_RE = re.compile(r'^#define\s+(\w+)', re.M)

# The header constants whose value `_DEFINE_RE` cannot read, because they are expressions over other
# constants rather than literals. A twin that restates one restates its RESULT, so the pin has to
# recompute the derivation here — spelt as the header spells it, over values the scraper CAN read.
# WITHOUT THIS THEY WERE SKIPPED IN SILENCE: `name in headers` was false, so the three most
# drift-prone values in `scroll_tile.S` (they move when MAP_COLUMN_BYTES or SCROLL_COLUMN_ROW_LONGS
# does, not when a literal is edited) were vouched for by a test that never looked at them.
ASM_DERIVED_PINS = {
    "SCROLL_TILE_ROW_BYTES": lambda d: 2 * d["SCROLL_COLUMN_ROW_LONGS"],
    "SCROLL_TILE_LAST_ROW": lambda d: d["SCROLL_TILE_BYTES"] - 2 * d["SCROLL_COLUMN_ROW_LONGS"],
    "SCROLL_MAP_PEEK_NEXT": lambda d: d["MAP_COLUMN_BYTES"] - 2,
    "PLAYFIELD_BOTTOM_Y": lambda d: d["PLAYFIELD_TOP_Y"] + d["PLAYFIELD_ROWS"],
    "SPRITE_CELL_HALF": lambda d: d["SPRITE_CELL_BYTES"] // d["SPRITE_CELL_LONGS"],
    "SPRITE_COLLIDE_LAST_CELL": lambda d: d["SCREEN_ROW_BYTES"] - d["SPRITE_CELL_BYTES"],
}


def _asm_objects():
    """[(source, object)] for every twin, or a failure naming the build step that makes them."""
    sources = sorted((REC / "src" / "asm").glob("*.S"))
    assert sources, "no twins in src/asm — this test would pass over any build at all"
    pairs = []
    for source in sources:
        obj = REC / "build" / "asm" / f"{source.stem}.o"
        assert obj.exists(), (
            f"{obj} is missing — the asm twins were never assembled. `make test` builds them "
            f"first; `make asm` builds them alone.")
        pairs.append((source, obj))
    return pairs


def _absolute_symbols(obj):
    """{name: value} for every absolute symbol in one object — which is what `.equ` produces."""
    return {name: addr for name, (addr, kind) in asm_twin.elf_symbols(obj).items() if kind == "a"}


def _header_defines():
    """{name: (value, header)} over every include/*.h — the side that owns these values."""
    out = {}
    for path in sorted((REC / "include").glob("*.h")):
        for name, value in _iter_defines(path.relative_to(REC)):
            out.setdefault(name, (value, path.name))
    return out


def _header_define_names():
    """Every name any include/*.h defines, readable value or not."""
    names = set()
    for path in sorted((REC / "include").glob("*.h")):
        names.update(_DEFINE_NAME_RE.findall(path.read_text()))
    return names


def test_asm_twin_equates_match_the_headers():
    """Every `.equ` in a twin whose name a header also defines must hold the header's value.

    NON-VACUOUS PER FILE, not per suite: each `.S` must contribute at least one pinned name, and is
    read from its OWN object so a neighbour's correct copy cannot vouch for it.
    """
    headers = _header_defines()
    header_names = _header_define_names()
    for source, obj in _asm_objects():
        equates = _absolute_symbols(obj)
        pinned = [name for name in _EQU_RE.findall(source.read_text()) if name in header_names]
        assert pinned, (
            f"src/asm/{source.name} declares no `.equ` that any include/*.h also defines, so nothing "
            f"in it is pinned. Name its constants as the headers name them (see src/asm/README.md).")
        for name in pinned:
            assert name in equates, (
                f"src/asm/{source.name} declares `.equ {name}` but its object has no such absolute "
                f"symbol — the scrape and the assembler disagree about what a `.equ` is")
            if name in headers:
                expected, header = headers[name]
            else:
                # A header expression rather than a literal. It still has to be pinned, so the
                # derivation is recomputed here rather than the name being skipped.
                assert name in ASM_DERIVED_PINS, (
                    f"src/asm/{source.name} restates {name}, which include/ defines as an expression "
                    f"this file's scraper cannot read. Add its derivation to ASM_DERIVED_PINS so the "
                    f"value is pinned — a name that is neither readable nor derived is UNPINNED, and "
                    f"silence there is what this test exists to prevent.")
                expected = ASM_DERIVED_PINS[name]({k: v for k, (v, _) in headers.items()})
                header = "a derived define, recomputed by ASM_DERIVED_PINS"
            assert equates[name] == expected, (
                f"src/asm/{source.name}'s {name} assembles to {equates[name]:#x}, but "
                f"include/{header} defines it as {expected:#x}")


# ==================================================== a verification-only twin's only surface

# WHY THIS EXISTS, and why it is scoped to the VERIFICATION-ONLY twins rather than to all of them.
#
# `atari/build.sh`'s asm-twin gate asks the OBJECTS two questions: is every declared twin defined,
# and is it called — or, for one marked `ZY_TWIN_VERIFICATION_ONLY` (include/asm_twin.h), NOT
# called. Neither question reaches the differential.
#
# A SHIPPED twin does not need this check: the game runs its instructions, so `atari/smoke.py`'s
# frame differential against the original is a surface it cannot lose. A twin that is verified and
# deliberately NOT shipped has no such thing — its object is dropped from the link, so delete
# `test/test_asm_frame_spawn.py` and `make test`, `build.sh game` and the whole smoke matrix stay
# green, because the last thing reading `frame_spawn.S` is an `as` invocation whose output is thrown
# away. The twin then rots silently against every later change to the C it stands for, which is the
# same "a check that stopped checking looks exactly like a clean build" failure the asm-twin gate
# itself exists to prevent.
#
# TWO BROADER DRAFTS OF THIS WERE WRONG, and both are worth recording because the obvious
# generalisation of this check does not work:
#   * over `.S` FILES, it reddened on `scroll_blit.S` and `scroll_emit.S`, which are thoroughly
#     tested — `test_asm_scroll.py` reaches their twins by SYMBOL and never writes a file name;
#   * over every twin SYMBOL, it reddened on the twenty `scroll_page_to_screen_p*_asm`, whose suite
#     builds their names with an f-string (`f"scroll_page_to_screen_p{phase:02d}_asm"`), so no
#     literal search can find them.
# A text search cannot answer "is this tested" in general. It CAN answer "does the file that is this
# twin's only reader still mention it", which is the whole of what the unshipped ones are missing.
_SUITE_GLOB = "test_asm_*.py"
_BUILD_SH = REC / "atari" / "build.sh"


def _gate_verification_only_twins():
    """`atari/build.sh`'s OWN scraper, extracted from the script and run over `include/*.h`.

    RUN RATHER THAN RE-SPELT. A Python mirror of the marker rule would be a second spelling with
    nothing holding it equal, and the set it would silently disagree about is exactly the twins that
    have no other surface. Extracting the shell function and invoking it means this file cannot
    check a different set than the gate does.
    """
    text = _BUILD_SH.read_text()
    helper_at = text.index("strip_comments() {")
    helper = text[helper_at:text.index("\n", helper_at) + 1]
    body_at = text.index("verification_only_twins() {")
    body = text[body_at:text.index("\n}\n", body_at) + 3]
    script = f"set -euo pipefail\nREC={REC}\n{helper}{body}\nverification_only_twins\n"
    done = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=True)
    return sorted(done.stdout.split())


@pytest.mark.parametrize("symbol", _gate_verification_only_twins() or [None])
def test_every_verification_only_twin_is_named_by_a_test_suite(symbol):
    """A twin the game does not call must still be named by the suite that verifies it."""
    if symbol is None:
        pytest.skip("no twin is declared ZY_TWIN_VERIFICATION_ONLY, so there is nothing to check")
    suites = sorted((REC / "test").glob(_SUITE_GLOB))
    assert suites, f"no {_SUITE_GLOB} in {REC / 'test'} — this check would pass over anything"
    naming = [suite.name for suite in suites if symbol in suite.read_text()]
    assert naming, (
        f"{symbol} is declared ZY_TWIN_VERIFICATION_ONLY, so the game never calls it and its object "
        f"is dropped from the link — and now no test suite names it either, which leaves the "
        f"assembler as its only reader. Give it a differential in test/{_SUITE_GLOB}, or delete the "
        f"twin and its declaration.")


def test_the_verification_only_twins_are_the_ones_this_wave_declared():
    """The scan's positive control: three, by name.

    Every case above is vacuous over an empty list, and the marker rule lives in a shell script this
    file cannot import — so a scraper that quietly stopped matching (a renamed macro, a moved
    anchor, grep's filename prefix) would take the whole section with it and look like a pass.
    """
    assert _gate_verification_only_twins() == [
        "frame_drone_and_fire_stage_asm",
        "frame_panel_scroll_and_ship_stage_asm",
        "frame_spawn_and_move_stage_asm",
    ], ("the set of verification-only twins moved. If that was deliberate, move this list; if the "
        "scan came back empty or wrong, atari/build.sh's marker scraper has stopped matching and "
        "every check in this section is passing over nothing")
