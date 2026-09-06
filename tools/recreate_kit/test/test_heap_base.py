"""The Malloc arena's base is PER PROJECT, and both sides must allocate from the same place.

`include/os.h` fixes the model's memory map kit-wide, but one region of it has to move: a program
whose bss covers 0x20000 (projects/bubbleghost's runs to 0x2520e) cannot share the default arena, and
os.h is compiled into two shared objects — the oracle every project links and the game's own
candidate — so a `#define` cannot answer "where" per project. `project.toml`'s optional `heap_base`
does, and `recreate_kit.harness` installs it into both `.so` files at import.

WHAT THIS PINS, in the three layers the value passes through:

  * **the key** — `project._heap_base` reads it, refuses a shape that is not an even address, and
    names the file to edit; and a `project.toml` carrying one really does reach `cfg.heap_base`.
  * **the place** — `harness._vet_os_memory_map` checks the CONFIGURED base against the program and
    against the model's other fixed regions. A base is now a project's own choice, so the arithmetic
    that was true by construction for a kit-wide constant has to be asserted: it can land inside the
    program, over the staged-file table, or on the harness-poked input block, and every one of those
    is SILENT — a Malloc block is a plain image write on both sides, so two corrupted runs compare
    equal.
  * **both sides** — the oracle's `Malloc` and the candidate's `OS_HEAP_BASE` report the same base,
    at the default and after a non-default one is installed. This is the case the whole mechanism
    exists for: a candidate served the old base while the oracle allocates from the new one would
    disagree by a whole arena, and only a comparison of what each side stored can say so.

The module skips whole when the shared oracle or a C compiler is absent — `oracle/build/` is
gitignored, so a bare checkout is a normal state to be in (`test_entry_state.py`'s convention).
Binding is process-wide and one-shot, which is why the `project.load` case below runs in a
subprocess: `kit_smoke_project.bind()` has already bound this one.
"""
import ctypes
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from kit_smoke_project import (HEAP_RESULT, LOAD_BASE, MALLOC_ENTRY, MALLOC_SIZED_ENTRY, bind,
                               malloc_size_poke)

harness = bind()
# All three are importable only once a project is bound, which bind() above is what does — and it
# also puts `reverse/tools` on sys.path, so `recreate_kit` resolves.
import emu            # noqa: E402
import loader         # noqa: E402
from recreate_kit import project   # noqa: E402

RECREATE_DIR = Path("/nowhere/projects/example/recreate")      # only ever formatted into a message

# A base the smoke project did not configure, well clear of its program, of the staged-file table and
# of HEAP_RESULT — so "the block moved" is the only reason a side could report it.
MOVED_BASE = 0x40000

# What a refusal must say about a base NOBODY configured. kit_smoke_project's project.toml carries no
# `heap_base`, so the reader has no such line to go and edit: the file to change is os.h.
DEFAULT_ATTRIBUTION = "`OS_HEAP_BASE_DEFAULT` in tools/recreate_kit/include/os.h"

# An object exporting no entry point at all — what a candidate or an oracle built before the key
# existed looks like to ctypes' attribute lookup (see test_a_side_that_cannot_be_told_is_refused).
_UNBOUND_LIB = object()


def _assert_attributes_the_base_to_os_h(message):
    """Every refusal about the smoke project's arena must name os.h and say the key is ABSENT.

    The three place-refusals used to assert only that the word `heap_base` appeared and that
    project.toml was named — which the old text satisfied by attributing an os.h default to a key
    that file does not contain, sending a reader to edit a line that is not there.
    """
    assert DEFAULT_ATTRIBUTION in message, message
    assert f"no `heap_base` in {project.current().dir / project.CONFIG_NAME}" in message, message


def _stored_base(image_writes):
    """The longword the oracle stored at HEAP_RESULT, out of its write set."""
    return int.from_bytes(bytes(image_writes[HEAP_RESULT + i] for i in range(4)), "big")


def _malloc_differential():
    """Run the .PRG's `Malloc(-1)` against the candidate that reads OS_HEAP_BASE for the same fact.

    The address to store at is passed to the glue rather than compiled into it, so the one spelling
    of HEAP_RESULT is kit_smoke_project's, beside the 68000 code that stores to the same place.
    """
    return harness.differential(MALLOC_ENTRY, {},
                                lambda lib, buf: lib.g_stores_the_heap_base(buf, HEAP_RESULT))


# ==================================================== the key

def test_an_absent_key_means_the_kit_default():
    """No `heap_base` in project.toml is None here and OS_HEAP_BASE_DEFAULT everywhere else.

    The default is C's (`os.h`'s OS_HEAP_BASE_DEFAULT, mirrored in emu.py and pinned equal by
    test_os_memory_map.py), so `project` — which emu imports, and so cannot import back — reports
    only the absence and lets emu resolve it.
    """
    assert project.current().heap_base is None
    assert emu.OS_HEAP_BASE == emu.OS_HEAP_BASE_DEFAULT
    assert harness.OS_HEAP_BASE == emu.OS_HEAP_BASE_DEFAULT


def test_an_explicit_base_is_read_as_written():
    assert project._heap_base({"heap_base": MOVED_BASE}, RECREATE_DIR) == MOVED_BASE


@pytest.mark.parametrize("value", ("0x30000", float(MOVED_BASE), True))
def test_a_base_that_is_not_an_integer_is_refused_and_names_the_file(value):
    """A quoted address is the plausible hand-edit, and `True` is the one an `isinstance(int)` test
    would let through — bool is a subclass of int, so `heap_base = true` would install base 1."""
    with pytest.raises(TypeError) as excinfo:
        project._heap_base({"heap_base": value}, RECREATE_DIR)
    assert str(RECREATE_DIR / project.CONFIG_NAME) in str(excinfo.value)
    assert "heap_base" in str(excinfo.value)


@pytest.mark.parametrize("value", (0x30001, 0, -0x30000))
def test_an_odd_or_non_positive_base_is_refused_and_names_the_file(value):
    """68000 code reads words from the block it is handed, so an odd arena is an address error on
    the machine while the model — which emulates none — would run on regardless."""
    with pytest.raises(ValueError) as excinfo:
        project._heap_base({"heap_base": value}, RECREATE_DIR)
    assert str(RECREATE_DIR / project.CONFIG_NAME) in str(excinfo.value)


def test_a_project_toml_carrying_the_key_reaches_the_config(tmp_path):
    """The wiring `_heap_base`'s own cases cannot see: that `load()` reads the key at all.

    In a subprocess because `project.load` binds one project per process and this one is already
    bound (`bind()` above). It needs no .PRG and no build — `load()` resolves paths and rebinds the
    loader's constants, and reads nothing.
    """
    (tmp_path / "project.toml").write_text(
        'name = "heap_base_probe"\nprg = "x.prg"\nnames = "x.txt"\nlib = "x.so"\n'
        f"load_base = {LOAD_BASE}\nimage_size = {loader.IMAGE_SIZE}\n"
        f"heap_base = {MOVED_BASE:#x}\n")
    script = textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {str(Path(project.__file__).resolve().parents[1])!r})
        from recreate_kit import project
        print(project.load({str(tmp_path)!r}).heap_base)
    """)
    out = subprocess.run([sys.executable, "-c", script], check=True, capture_output=True, text=True)
    assert int(out.stdout.strip()) == MOVED_BASE


# ==================================================== the place

def test_the_bound_projects_own_map_is_accepted():
    """The control: re-running the import-time check unchanged raises nothing, so every refusal
    below is the base this case moved and not some other disagreement in the map."""
    harness._vet_os_memory_map()


def test_a_base_inside_the_program_is_refused_by_name(monkeypatch):
    """The original check, still armed now that the address is the project's to choose: a block
    handed out here lands on the program's own code, identically on both sides."""
    monkeypatch.setattr(emu, "OS_HEAP_BASE", LOAD_BASE + 2)
    with pytest.raises(RuntimeError) as excinfo:
        harness._vet_os_memory_map()
    message = str(excinfo.value)
    assert "Malloc arena" in message
    _assert_attributes_the_base_to_os_h(message)


def test_the_waiver_still_covers_a_base_inside_the_program(monkeypatch):
    """`tos_malloc_unused` waives exactly what it always did — the overlap, and nothing else.

    Its per-run half is unchanged too: `emu._vet_no_malloc_over_program` still fails any run that
    serves a Malloc while the overlap holds (projects/joust's test_heap_guard.py exercises it).
    """
    monkeypatch.setattr(emu, "OS_HEAP_BASE", LOAD_BASE + 2)
    monkeypatch.setattr(project.current(), "tos_malloc_unused", True)
    harness._vet_os_memory_map()


def test_a_base_over_the_staged_file_table_is_refused_by_name(monkeypatch):
    """The arena grows UP without bound, so a base at the table's address overwrites the very
    entries the harness stages files into — and nothing else watches that region."""
    monkeypatch.setattr(emu, "OS_HEAP_BASE", harness.OS_FS_TABLE)
    with pytest.raises(RuntimeError) as excinfo:
        harness._vet_os_memory_map()
    message = str(excinfo.value)
    assert "OS_FS_TABLE" in message
    _assert_attributes_the_base_to_os_h(message)


def test_a_base_over_the_staged_file_table_is_refused_even_under_the_waiver(monkeypatch):
    """`tos_malloc_unused` is a claim about the PROGRAM's extent, so it must not reach this one.

    The two refusals sit either side of it in `_vet_os_memory_map`, and a waiver written to permit
    an overlap with the program would otherwise be read as permission to allocate anywhere.
    """
    monkeypatch.setattr(emu, "OS_HEAP_BASE", harness.OS_FS_TABLE)
    monkeypatch.setattr(project.current(), "tos_malloc_unused", True)
    with pytest.raises(RuntimeError, match="OS_FS_TABLE"):
        harness._vet_os_memory_map()


def test_a_base_on_the_poked_input_block_is_refused_by_name(monkeypatch):
    """The other end of the image: a block handed out below 0x620 covers the model's own console,
    Random and PSG state, which both sides then read as a game's allocation.

    The phrase is "console-key poke block", NOT "poked input block": two sibling suites
    (projects/joust's test_os_traps.py, projects/wonderboy's test_poked_input_guard.py) match the
    latter to pin the OVERLAP refusal at the end of _vet_os_memory_map, and a second refusal
    carrying it would let those cases pass on this one.
    """
    monkeypatch.setattr(emu, "OS_HEAP_BASE", harness.OS_CON_PENDING)
    with pytest.raises(RuntimeError) as excinfo:
        harness._vet_os_memory_map()
    message = str(excinfo.value)
    assert "console-key poke block" in message and "OS_POKE_BLOCK_END" in message
    assert "poked input block" not in message, (
        "this refusal is matched by two sibling suites' pins on a DIFFERENT check")
    _assert_attributes_the_base_to_os_h(message)


def test_a_base_inside_the_framebuffer_is_refused_by_name(monkeypatch):
    """A game handed OS_SCREEN_BASE by Physbase/Logbase draws a whole frame over it, so a block
    handed out in that band is trampled mid-run — identically on both sides, hence silently."""
    monkeypatch.setattr(emu, "OS_HEAP_BASE", harness.OS_SCREEN_BASE)
    with pytest.raises(RuntimeError) as excinfo:
        harness._vet_os_memory_map()
    message = str(excinfo.value)
    assert "framebuffer" in message and "OS_SCREEN_BASE" in message
    _assert_attributes_the_base_to_os_h(message)


def test_a_configured_base_is_attributed_to_the_project_that_set_it(monkeypatch):
    """The other half of the attribution: with the key SET, the file to edit is project.toml.

    One refusal is enough to pin the phrase — every clause formats the same `heap_base_source()`.
    """
    monkeypatch.setattr(project.current(), "heap_base", MOVED_BASE)
    monkeypatch.setattr(emu, "OS_HEAP_BASE", harness.OS_FS_TABLE)
    with pytest.raises(RuntimeError) as excinfo:
        harness._vet_os_memory_map()
    message = str(excinfo.value)
    assert f"`heap_base` in {project.current().dir / project.CONFIG_NAME}" in message
    assert "OS_HEAP_BASE_DEFAULT" not in message, (
        "the project configured a base, so os.h's default is not what it is running on")


def test_a_ceiling_at_or_below_the_base_is_refused(monkeypatch):
    """`heap_limit` narrows the window; one at the base leaves no window, so every allocating run
    would be refused per run with a message about growth rather than about the configuration."""
    monkeypatch.setattr(emu, "HEAP_LIMIT", emu.OS_HEAP_BASE)
    with pytest.raises(RuntimeError, match="heap_limit"):
        harness._vet_os_memory_map()


# ==================================================== the two installers

@pytest.mark.parametrize("module, symbol, names", (
    (emu, "osh_set_heap_base", "liboracle.so"),
    (harness, "os_set_heap_base", "os_heap.c"),
))
def test_a_side_that_cannot_be_told_is_refused_by_name(module, symbol, names):
    """A .so predating the entry point must fail LOUDLY, naming the symbol and the rebuild.

    NEITHER REFUSAL HAD A SURFACE. Both are gated on the base being non-default, so no project in
    the tree and no suite here ever reached them: deleting either `raise` left every test green,
    and the failure it was written for — a stale build silently allocating from 0x20000 while the
    oracle allocates from the configured base — would have arrived as a whole-arena diff with no
    diagnostic. Passing an object with no such attribute is what drives them.
    """
    with pytest.raises(RuntimeError) as excinfo:
        emu.install_heap_base(_UNBOUND_LIB, symbol, MOVED_BASE, module._missing_heap_base_abi)
    message = str(excinfo.value)
    assert symbol in message and names in message
    assert "make" in message, "a refusal about a stale build must name the command that rebuilds it"


@pytest.mark.parametrize("symbol", ("osh_set_heap_base", "os_set_heap_base"))
def test_a_default_base_needs_no_entry_point_at_all(symbol):
    """...and the deliberate hole in it: a build predating the key already starts its arena at
    OS_HEAP_BASE_DEFAULT, so a project that configured nothing is served correctly by an old .so.

    Without this the guard above would be a compatibility break dressed as a safety check.
    """
    def _refuse(sym):
        raise AssertionError(f"install_heap_base asked for {sym} at the default base")

    assert emu.install_heap_base(_UNBOUND_LIB, symbol, emu.OS_HEAP_BASE_DEFAULT, _refuse) is False


# ==================================================== how far the arena may grow

def _run_a_malloc_of(size):
    """Run the .PRG's sized `Malloc` stub under the oracle, asking for `size` bytes."""
    return emu.run(harness.make_image(malloc_size_poke(size)), MALLOC_SIZED_ENTRY, {})


def test_an_allocation_inside_the_window_is_served():
    """The control: the guard below is about the CEILING and not about allocating at all."""
    _final, _writes, out_regs = _run_a_malloc_of(0x1000)
    assert out_regs["d0"] == emu.OS_HEAP_BASE
    assert out_regs["heap"] == emu.OS_HEAP_BASE + 0x1000


def test_an_allocation_past_the_ceiling_is_refused():
    """The arena grows UP without bound and only its BASE was ever vetted, so an allocation past
    the staged-file table overwrote it on both sides and the two corrupted runs compared equal."""
    with pytest.raises(AssertionError) as excinfo:
        _run_a_malloc_of(emu.HEAP_LIMIT - emu.OS_HEAP_BASE + 2)
    message = str(excinfo.value)
    assert "OS_FS_TABLE" in message and f"{emu.HEAP_LIMIT:#x}" in message


def test_an_allocation_exactly_to_the_ceiling_is_served():
    """The boundary, stated rather than left to the comparison: the ceiling is the first address
    the arena may NOT occupy, so a block ENDING there is the largest legal one."""
    _final, _writes, out_regs = _run_a_malloc_of(emu.HEAP_LIMIT - emu.OS_HEAP_BASE)
    assert out_regs["heap"] == emu.HEAP_LIMIT


def test_a_projects_own_ceiling_narrows_the_window_and_is_named(monkeypatch):
    """`heap_limit` is for a project whose free window ends below the table — because its own
    scratch map, or a region its cases poke, sits there. The refusal must name the key, not os.h."""
    narrowed = emu.OS_HEAP_BASE + 0x1000
    monkeypatch.setattr(project.current(), "heap_limit", narrowed)
    monkeypatch.setattr(emu, "HEAP_LIMIT", narrowed)
    with pytest.raises(AssertionError) as excinfo:
        _run_a_malloc_of(0x1002)
    message = str(excinfo.value)
    assert f"`heap_limit` in {project.current().dir / project.CONFIG_NAME}" in message
    assert "OS_FS_TABLE" not in message, "the project set its own ceiling; the table is not it"


@pytest.mark.parametrize("configured, expected", (
    (None, harness.OS_FS_TABLE),                             # no key: the kit's own ceiling
    (harness.OS_FS_TABLE - 0x1000, harness.OS_FS_TABLE - 0x1000),   # a narrower window is kept
    (harness.OS_FS_TABLE + 0x1000, harness.OS_FS_TABLE),     # ...a wider one is clamped
))
def test_a_project_may_only_lower_the_ceiling(configured, expected):
    """Raising it would let the arena over the staged-file table, which is what the kit-wide limit
    exists to stop — so the resolved value is the smaller of the two, not the project's."""
    assert emu.resolve_heap_limit(configured) == expected
    assert emu.HEAP_LIMIT == emu.resolve_heap_limit(project.current().heap_limit), (
        "the bound project's ceiling is not what emu resolved at import")


def test_the_harness_name_for_the_base_is_a_live_read_of_the_oracles(monkeypatch):
    """One value, not two. `harness.OS_HEAP_BASE` used to be a copy taken at import, so a test that
    moved the base — as the cases above do, and as `moved_heap_base` does for real — left the two
    modules disagreeing about which arena the run was using."""
    monkeypatch.setattr(emu, "OS_HEAP_BASE", MOVED_BASE)
    assert harness.OS_HEAP_BASE == MOVED_BASE


def test_the_star_export_still_carries_the_served_name():
    """...and serving it must not cost the projects their spelling of it.

    Every project's `test/harness.py` is `from recreate_kit.harness import *`, and two heap-guard
    suites read `harness.OS_HEAP_BASE` through that shim. A star-import copies the module's
    __dict__, which a name served by __getattr__ is NOT in — so harness.py's `__all__` has to list
    it, and without this case the omission would surface only as an AttributeError inside another
    project's suite.
    """
    namespace = {}
    exec("from recreate_kit.harness import *", namespace)     # noqa: S102 — the shims' own idiom
    assert namespace["OS_HEAP_BASE"] == emu.OS_HEAP_BASE


# ==================================================== both sides

def test_both_sides_allocate_from_the_default_base():
    """`Malloc(-1)` — the "largest free block?" query — is served fully and rounds to a zero-size
    bump, so it reports the arena's base without moving the pointer. The oracle's answer, the bytes
    it stored and the candidate's own reading of OS_HEAP_BASE must all be that base."""
    diffs, info = _malloc_differential()
    assert diffs == [], "the candidate read a different arena base from the one the oracle served"
    assert info["regs"]["d0"] == emu.OS_HEAP_BASE_DEFAULT
    assert _stored_base(info["writes"]) == emu.OS_HEAP_BASE_DEFAULT
    assert info["regs"]["heap"] == emu.OS_HEAP_BASE_DEFAULT, "Malloc(-1) must not move the pointer"


def test_both_sides_follow_the_base_to_a_new_address(moved_heap_base):
    """THE CASE THE MECHANISM EXISTS FOR: install a different base and both sides go with it.

    Installed through the same two entry points `emu`/`harness` use at import, so what this drives is
    the shipped path. A candidate that did not follow — one built before `src/os_heap.c` existed, or
    a shim whose `g_heap_base` were still a `#define` — would report the old base and diff by a whole
    arena, which is exactly the difference `diffs == []` is asked about here.
    """
    diffs, info = _malloc_differential()
    assert diffs == [], "the two sides disagree about where the moved arena starts"
    assert info["regs"]["d0"] == moved_heap_base
    assert _stored_base(info["writes"]) == moved_heap_base


@pytest.fixture
def moved_heap_base(monkeypatch):
    """Install MOVED_BASE on both sides for one test, and put the default back afterwards.

    Restored rather than left, because the binding — and so both `.so` files — is shared by every
    suite in this process (`kit_smoke_project`, "BINDING IS PROCESS-WIDE AND ONE-SHOT").
    """
    for lib, symbol in ((emu._LIB, "osh_set_heap_base"), (harness._lib, "os_set_heap_base")):
        getattr(lib, symbol).argtypes = [ctypes.c_uint32]
    def install(base):
        emu._LIB.osh_set_heap_base(base)
        harness._lib.os_set_heap_base(base)
    install(MOVED_BASE)
    # ...and the Python mirror of it, so the guards that read emu.OS_HEAP_BASE describe the arena
    # the two .so files are really using rather than the one they were imported with.
    monkeypatch.setattr(emu, "OS_HEAP_BASE", MOVED_BASE)
    try:
        yield MOVED_BASE
    finally:
        install(emu.OS_HEAP_BASE_DEFAULT)
