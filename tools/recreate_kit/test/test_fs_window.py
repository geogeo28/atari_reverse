"""The staged-file window is PER PROJECT, and both sides must read it in the same place.

`include/os.h` fixes the model's memory map kit-wide, but a second region of it has to move. The
table at `OS_FS_TABLE_DEFAULT` leaves `[0xc0000, STACK_GUARD_LO)` = 258,048 bytes for staged file
bytes, and a boot that opens more than that cannot be replayed whole: Flying Shark's opens eight
files totalling 288,551. `project.toml`'s optional `fs_base` places the table (the staging area
follows a fixed `OS_FS_STAGING_OFFSET` above it), and `recreate_kit.harness` installs it into both
`.so` files at import — os.h is compiled into two shared objects, so a `#define` cannot answer
"where" per project.

WHAT THIS PINS, in the three layers the value passes through:

  * **the key** — `project._fs_base` reads it, refuses a shape that is not an even address, and
    names the file to edit; and a `project.toml` carrying one really does reach `cfg.fs_base`.
  * **the place** — `harness._vet_staged_file_window` checks the CONFIGURED base against the
    program, the poked-input block, the framebuffer and the stack guard. Every one of those is
    SILENT otherwise: a staged file is a plain image write on both sides, so two corrupted runs
    compare equal. The arena needs no clause of its own, and the case below says why.
  * **both sides** — the oracle's `Fopen`/`Fread` traps and the candidate's `os_fopen`/`os_fread`
    resolve the same moved table and serve the same bytes, for a set of files the DEFAULT window
    cannot hold. That is the case the whole mechanism exists for.

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

from kit_smoke_project import (FS_BUF_AT, FS_NAME_AT, FS_READ_BYTES, FS_RESULT_AT, FS_STAGED_NAME,
                               LOAD_BASE, STAGED_FILE_ENTRY, bind)

harness = bind()
# All three are importable only once a project is bound, which bind() above is what does — and it
# also puts `reverse/tools` on sys.path, so `recreate_kit` resolves.
import emu            # noqa: E402
import loader         # noqa: E402
from recreate_kit import os_map, project   # noqa: E402

RECREATE_DIR = Path("/nowhere/projects/example/recreate")      # only ever formatted into a message

# Where Flying Shark's own window starts, and the value that made this mechanism necessary: its
# program ends at 0x5aede and its `abi` scratch map runs to 0xb1000, so 0xb7000 is the lowest table
# that clears both — and it buys 290,816 staging bytes where the default buys 258,048.
MOVED_BASE = 0xB7000

# The file bytes the differential really moves, and a set of RESERVATIONS that does not fit the
# default window. `stage_files` lays each file out past the previous one's reservation, so four
# 70,000-byte claims span 280,000 bytes: from the moved staging area they end below the stack guard,
# from the default one they run past it. Small `data` behind big `capacity` keeps the pokes tiny —
# what is under test is where the window IS, not how long a poke can be.
STAGED_DATA = bytes(range(FS_READ_BYTES))
RESERVATION = 70_000
FILLER_FILES = 3
FILLER_NAME = "FILLER%d.DAT"


def _staged_files():
    """The staged set: three reservations, then the file the .PRG opens, at the far end of them."""
    return [(FILLER_NAME % i, b"", RESERVATION) for i in range(FILLER_FILES)] + \
           [(FS_STAGED_NAME, STAGED_DATA, RESERVATION)]


def _name_poke():
    """The filename the .PRG's `Fopen` points at, NUL-terminated, at FS_NAME_AT."""
    return {FS_NAME_AT: FS_STAGED_NAME.encode("ascii") + b"\0"}


# ==================================================== the key

def test_an_absent_key_means_the_kit_default():
    """No `fs_base` in project.toml is None here and OS_FS_TABLE_DEFAULT everywhere else.

    The default is C's (`os.h`'s OS_FS_TABLE_DEFAULT, mirrored in os_map.py and pinned equal by
    test_os_memory_map.py), so `project` — which emu imports, and so cannot import back — reports
    only the absence and lets emu resolve it.
    """
    assert project.current().fs_base is None
    assert emu.OS_FS_TABLE == os_map.OS_FS_TABLE_DEFAULT
    assert harness.OS_FS_TABLE == os_map.OS_FS_TABLE_DEFAULT


def test_the_staging_area_follows_the_table():
    """One key places both halves: the raw bytes start a fixed distance above the table, so a moved
    window can never put the table over its own staging area."""
    assert emu.OS_FS_STAGING == emu.OS_FS_TABLE + os_map.OS_FS_STAGING_OFFSET
    assert harness.OS_FS_STAGING == emu.OS_FS_STAGING


def test_an_explicit_base_is_read_as_written():
    assert project._fs_base({"fs_base": MOVED_BASE}, RECREATE_DIR) == MOVED_BASE


@pytest.mark.parametrize("value", ("0xb7000", float(MOVED_BASE), True))
def test_a_base_that_is_not_an_integer_is_refused_and_names_the_file(value):
    """A quoted address is the plausible hand-edit, and `True` is the one an `isinstance(int)` test
    would let through — bool is a subclass of int, so `fs_base = true` would install base 1."""
    with pytest.raises(TypeError) as excinfo:
        project._fs_base({"fs_base": value}, RECREATE_DIR)
    assert str(RECREATE_DIR / project.CONFIG_NAME) in str(excinfo.value)
    assert "fs_base" in str(excinfo.value)


@pytest.mark.parametrize("value", (MOVED_BASE + 1, 0, -MOVED_BASE))
def test_an_odd_or_non_positive_base_is_refused_and_names_the_file(value):
    """Every field of a table entry is a longword the model reads and writes, and 68000 code handed
    a staged file's address takes words out of it."""
    with pytest.raises(ValueError) as excinfo:
        project._fs_base({"fs_base": value}, RECREATE_DIR)
    assert str(RECREATE_DIR / project.CONFIG_NAME) in str(excinfo.value)


def test_a_project_toml_carrying_the_key_reaches_the_config(tmp_path):
    """The wiring `_fs_base`'s own cases cannot see: that `load()` reads the key at all.

    In a subprocess because `project.load` binds one project per process and this one is already
    bound (`bind()` above). It needs no .PRG and no build — `load()` resolves paths and rebinds the
    loader's constants, and reads nothing.
    """
    (tmp_path / "project.toml").write_text(
        'name = "fs_base_probe"\nprg = "x.prg"\nnames = "x.txt"\nlib = "x.so"\n'
        f"load_base = {LOAD_BASE}\nimage_size = {loader.IMAGE_SIZE}\n"
        f"fs_base = {MOVED_BASE:#x}\n")
    script = textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {str(Path(project.__file__).resolve().parents[1])!r})
        from recreate_kit import project
        print(project.load({str(tmp_path)!r}).fs_base)
    """)
    out = subprocess.run([sys.executable, "-c", script], check=True, capture_output=True, text=True)
    assert int(out.stdout.strip()) == MOVED_BASE


# ==================================================== the place

def test_the_bound_projects_own_window_is_accepted():
    """The control: re-running the import-time check unchanged raises nothing, so every refusal
    below is the window this case moved and not some other disagreement in the map."""
    harness._vet_staged_file_window()


def _refusal_for(table, monkeypatch):
    """Move the window to `table` and return what `_vet_staged_file_window` refuses it with."""
    monkeypatch.setattr(emu, "OS_FS_TABLE", table)
    monkeypatch.setattr(emu, "OS_FS_STAGING", table + os_map.OS_FS_STAGING_OFFSET)
    with pytest.raises(RuntimeError) as excinfo:
        harness._vet_staged_file_window()
    return str(excinfo.value)


def test_a_window_inside_the_program_is_refused_by_name(monkeypatch):
    """The table and every file staged behind it would land on the program's own code/bss —
    identically on both sides, so nothing else in the harness could see it."""
    message = _refusal_for(LOAD_BASE + 2, monkeypatch)
    assert f"{loader.PROGRAM_END:#x}" in message and "program" in message
    assert "OS_FS_TABLE_DEFAULT" in message, "the project set no key; the file to edit is os.h"


def test_a_window_on_the_poked_input_block_is_refused_by_name(monkeypatch):
    """The other end of the image: a table at 0x600 covers the model's own console, Random and PSG
    state, which both sides then read back as a staged file's entry."""
    message = _refusal_for(harness.OS_CON_PENDING, monkeypatch)
    assert "console-key poke block" in message and "OS_POKE_BLOCK_END" in message


def test_a_window_inside_the_framebuffer_is_refused_by_name(monkeypatch):
    """A game handed OS_SCREEN_BASE by Physbase/Logbase draws a whole frame over the table and the
    files behind it, so a window in that band is trampled mid-run on both sides."""
    message = _refusal_for(harness.OS_SCREEN_BASE, monkeypatch)
    assert "framebuffer" in message and "OS_SCREEN_BASE" in message


def test_a_window_reaching_the_stack_guard_is_refused_by_name(monkeypatch):
    """Staging at or above the guard puts file bytes in the band the differential DROPS, so a
    candidate that read the wrong ones would never be compared on them."""
    message = _refusal_for(emu.STACK_GUARD_LO, monkeypatch)
    assert f"{emu.STACK_GUARD_LO:#x}" in message and "stack guard" in message


def test_the_import_time_check_runs_this_one_too(monkeypatch):
    """The wiring: `_vet_os_memory_map` — the check every bound project passes at import — is what
    calls the four clauses above. Driven with the window moved past the stack guard because that is
    the one collision no earlier clause there reaches first, so a raise really is this one.
    """
    monkeypatch.setattr(emu, "OS_FS_TABLE", emu.STACK_GUARD_LO)
    monkeypatch.setattr(emu, "OS_FS_STAGING", emu.STACK_GUARD_LO + os_map.OS_FS_STAGING_OFFSET)
    with pytest.raises(RuntimeError, match="stack guard"):
        harness._vet_os_memory_map()


def test_a_configured_base_is_attributed_to_the_project_that_set_it(monkeypatch):
    """The other half of the attribution: with the key SET, the file to edit is project.toml.

    One refusal is enough to pin the phrase — every clause formats the same `fs_base_source()`.
    """
    monkeypatch.setattr(project.current(), "fs_base", MOVED_BASE)
    message = _refusal_for(LOAD_BASE + 2, monkeypatch)
    assert f"`fs_base` in {project.current().dir / project.CONFIG_NAME}" in message
    assert "OS_FS_TABLE_DEFAULT" not in message, (
        "the project configured a base, so os.h's default is not what it is running on")


def test_moving_the_window_down_lowers_the_arenas_ceiling(monkeypatch):
    """WHY THE WINDOW NEEDS NO ARENA CLAUSE OF ITS OWN: the heap's ceiling IS the table's address.

    A project that moves its window down moves the ceiling with it, so the arena cannot grow into
    the table — and `_vet_os_memory_map`'s existing `heap_base >= OS_FS_TABLE` refusal covers the
    other direction. A clamp against os.h's DEFAULT instead would leave both silently open.
    """
    monkeypatch.setattr(emu, "OS_FS_TABLE", MOVED_BASE)
    assert emu.resolve_heap_limit(None) == MOVED_BASE
    assert emu.resolve_heap_limit(os_map.OS_FS_TABLE_DEFAULT) == MOVED_BASE


# ==================================================== the two installers

@pytest.mark.parametrize("module, symbol, names", (
    (emu, "osh_set_fs_table", "liboracle.so"),
    (harness, "os_set_fs_table", "os_fs.c"),
))
def test_a_side_that_cannot_be_told_is_refused_by_name(module, symbol, names):
    """A .so predating the entry point must fail LOUDLY, naming the symbol and the rebuild.

    Both refusals are gated on the base being non-default, so no project in the tree reaches them;
    passing an object with no such attribute is what drives them (test_heap_base.py's argument).
    """
    with pytest.raises(RuntimeError) as excinfo:
        emu.install_fs_table(object(), symbol, MOVED_BASE, module._missing_fs_table_abi)
    message = str(excinfo.value)
    assert symbol in message and names in message
    assert "make" in message, "a refusal about a stale build must name the command that rebuilds it"


@pytest.mark.parametrize("symbol", ("osh_set_fs_table", "os_set_fs_table"))
def test_a_default_base_needs_no_entry_point_at_all(symbol):
    """...and the deliberate hole in it: a build predating the key already reads the table at
    OS_FS_TABLE_DEFAULT, so a project that configured nothing is served correctly by an old .so."""
    def _refuse(sym):
        raise AssertionError(f"install_fs_table asked for {sym} at the default base")

    assert emu.install_fs_table(object(), symbol, os_map.OS_FS_TABLE_DEFAULT, _refuse) is False


# ==================================================== both sides

def test_the_default_window_cannot_hold_the_staged_set():
    """The control the moved-window case rests on: at the DEFAULT base these files do not fit.

    Without it "the moved window staged them" would be a claim about nothing — the default window
    might have held them all along, and the case below would pass with the mechanism deleted.
    """
    with pytest.raises(AssertionError, match="overflowed the stack guard"):
        harness.stage_files(_staged_files())


def test_both_sides_read_a_file_the_default_window_could_not_hold(moved_fs_window):
    """THE CASE THE MECHANISM EXISTS FOR: install a different base and both sides go with it.

    The oracle reaches the file through its GEMDOS `Fopen`/`Fread` traps and the candidate through
    os.h's `os_fopen`/`os_fread`, so what this compares is the table each resolved and the bytes each
    copied. A side still reading the default table would find no such name, refuse, and raise —
    which is why `diffs == []` here is a statement about BOTH.
    """
    pokes, handles = harness.stage_files(_staged_files())
    pokes.update(_name_poke())
    diffs, info = harness.differential(
        STAGED_FILE_ENTRY, {"_pokes": pokes},
        lambda lib, buf: lib.g_reads_a_staged_file(buf, FS_NAME_AT, FS_READ_BYTES, FS_BUF_AT,
                                                  FS_RESULT_AT))
    assert diffs == [], "the two sides disagree about the moved staged-file window"
    assert info["regs"]["d0"] == FS_READ_BYTES, "Fread did not find the file at the moved table"
    assert handles[FS_STAGED_NAME] == harness.OS_FS_FIRST_HANDLE + FILLER_FILES
    # ...and WHICH bytes, from the oracle's final image rather than from `info["writes"]`: os_fread
    # copies into the image with a memcpy that never passes through the shim's write callbacks, so
    # a served file leaves no entry in the write ledger at all.
    mem, _writes, _regs = emu.run(harness.make_image(pokes), STAGED_FILE_ENTRY)
    assert mem[FS_BUF_AT:FS_BUF_AT + FS_READ_BYTES] == STAGED_DATA, (
        "the bytes served are not the ones staged at the moved window")


def test_the_moved_table_is_where_the_entries_were_written(moved_fs_window):
    """...and the addresses themselves, so the case above cannot pass on a window that never moved:
    every table entry lands at the MOVED base, and every file's bytes above it."""
    files = _staged_files()
    pokes, _handles = harness.stage_files(files)
    entries = [moved_fs_window + slot * harness.OS_FS_ENTRY for slot in range(len(files))]
    assert set(entries) <= set(pokes), "the table entries are not at the moved base"
    staging = sorted(set(pokes) - set(entries))
    assert staging[0] == moved_fs_window + os_map.OS_FS_STAGING_OFFSET, (
        "the first file's bytes do not start at the moved staging area")
    assert staging[-1] < emu.STACK_GUARD_LO, "a staged file ran into the stack guard"


@pytest.fixture
def moved_fs_window(monkeypatch):
    """Install MOVED_BASE on both sides for one test, and put the default back afterwards.

    Restored rather than left, because the binding — and so both `.so` files — is shared by every
    suite in this process (`kit_smoke_project`, "BINDING IS PROCESS-WIDE AND ONE-SHOT").
    """
    for lib, symbol in ((emu._LIB, "osh_set_fs_table"), (harness._lib, "os_set_fs_table")):
        getattr(lib, symbol).argtypes = [ctypes.c_uint32]

    def install(base):
        emu._LIB.osh_set_fs_table(base)
        harness._lib.os_set_fs_table(base)

    install(MOVED_BASE)
    # ...and the Python mirror of it, so `stage_files` and every guard describe the window the two
    # .so files are really using rather than the one they were imported with.
    monkeypatch.setattr(emu, "OS_FS_TABLE", MOVED_BASE)
    monkeypatch.setattr(emu, "OS_FS_STAGING", MOVED_BASE + os_map.OS_FS_STAGING_OFFSET)
    try:
        yield MOVED_BASE
    finally:
        install(os_map.OS_FS_TABLE_DEFAULT)
