"""`derived.kept` held to its one promise: an answer is served only to the question it answered — the same tree, the
same base image, the same deriving function, the same arguments by value — and a stale one cannot be: each test
below changes ONE of those and requires the derivation made again. Over a cache directory of the test's own.
"""
import functools
import os
import pickle
import signal
import struct
import subprocess
import sys
import time
import types
from collections import namedtuple
from pathlib import Path

import pytest

import derived
import fork_pool
import harness
from harness import BASE_IMAGE, addrs, make_image


@pytest.fixture(autouse=True)
def a_cache_of_the_test_s_own(tmp_path, monkeypatch):
    """Every test here keeps its answers under its own directory, switched ON whatever the run's environment says —
    and none of them made again as a sample (the tests of the sample ask for it: most derivations here COUNT how
    often they are made). It begins holding no claim, whatever a test before it left held as it failed."""
    monkeypatch.setattr(derived, "ROOT", tmp_path / "derived")
    monkeypatch.setattr(derived, "_CLAIMS_HELD", [])
    monkeypatch.delenv(derived.DERIVED_OFF, raising=False)
    monkeypatch.setattr(derived, "_candidate_is_the_project_s", lambda: True)
    monkeypatch.setattr(derived, "SAMPLED_ONE_IN", 0)


_MADE = {}                              # {a counted derivation's number: the calls that MADE it}


def _counted(steady=None):
    """A derivation that counts how often it is MADE: `(the kept function, the calls made)` — answering how often,
    or `steady`, the same whenever it is made. The count is kept where the deriver does not CLOSE over it: what a
    deriver closes over is part of which deriver it is (a list that grew would make it another function at every
    call)."""
    number = len(_MADE)
    made = _MADE[number] = []

    def answer_of(*arguments, **named):
        _MADE[number].append((arguments, named))
        return {"made": len(_MADE[number])} if steady is None else steady
    return derived.kept(answer_of), made


def _kept_files():
    return sorted(path for path in derived.ROOT.rglob("*") if path.is_file())


# ---- the same question is answered once ------------------------------------------------------------------------------
def test_an_answer_is_made_once_and_served_to_the_same_question_after():
    asked, made = _counted()
    first = asked(1, b"two", pokes={0x100: b"\x01\x02"})
    assert asked(1, b"two", pokes={0x100: b"\x01\x02"}) == first and len(made) == 1
    assert [path.suffix for path in _kept_files()] == [".pickle"], "one answer kept, and no scratch file left"
    assert _kept_files()[0].parent.parent.name == derived.tree_key(), "kept under the tree it was derived by"


def test_a_miss_answers_what_a_hit_answers_not_the_deriver_s_own_object():
    """The answer of the call that MADE it is the kept bytes read back — the object a later hit gets, type for type —
    so a cold run and a warm one hand a case the same thing; and what a caller does to its answer reaches no other."""
    handed = [{"a": bytearray(b"\x01"), "b": (1, [2])}]
    asked = derived.kept(lambda: handed[0])
    cold = asked()
    assert cold == handed[0] and cold is not handed[0] and type(cold["a"]) is bytearray
    cold["a"][0] = 0xFF
    assert asked() == {"a": bytearray(b"\x01"), "b": (1, [2])}


# ---- THE RED TESTS: one thing of the question changed, the derivation made again ---------------------------------------
Shape = namedtuple("Shape", "path waits")
Other = namedtuple("Other", "path waits")


def _closing_over(value):
    return lambda: value


def _with_attribute(value):
    def function():
        return None
    function.asks = value
    return function


def _with_default(value):
    def function(by=value):
        return by
    return function


class _Schedule:
    """An object of a class that SAYS what a derivation is asked about of it (`derived.ASKED_ABOUT`): its rows — not
    how far a run has counted through them."""

    def __init__(self, rows, counted):
        self.rows, self.counted = rows, counted

    def derived_content(self):
        return self.rows


CHANGED_INPUTS = {
    "a number": ((1,), (2,)),
    "a number and the string that spells it": ((1,), ("1",)),
    "True and 1": ((True,), (1,)),
    "a byte of a string of bytes": ((b"\x00\x01",), (b"\x00\x02",)),
    "one poke's byte": (({0x100: b"\x01\x02", 0x200: b"\x03"},), ({0x100: b"\x01\x02", 0x200: b"\x04"},)),
    "one poke's address": (({0x100: b"\x01\x02"},), ({0x101: b"\x01\x02"},)),
    "where two pokes are cut": (({0x100: b"\x01\x02"},), ({0x100: b"\x01", 0x101: b"\x02"},)),
    "a tuple and the list of the same": (((1, 2),), ([1, 2],)),
    "a dict's value": (({"a": 1},), ({"a": 2},)),
    "a set's member": ((frozenset({1, 2}),), (frozenset({1, 3}),)),
    "a named tuple's field": ((Shape("A:\\", 1),), (Shape("A:\\", 2),)),
    "a named tuple's own type": ((Shape("A:\\", 1),), (Other("A:\\", 1),)),
    "a struct's format": ((struct.Struct(">hI"),), (struct.Struct(">hH"),)),
    "a range's end": ((range(3),), (range(4),)),
    "what a function closes over": ((_closing_over(1),), (_closing_over(2),)),
    "a function's own attribute": ((_with_attribute(True),), (_with_attribute(False),)),
    "a function's default": ((_with_default(1),), (_with_default(2),)),
    "which function it is": ((_closing_over,), (_with_default,)),
    "a partial's argument": ((functools.partial(_closing_over, 1),), (functools.partial(_closing_over, 2),)),
    "the function a cache wraps": ((functools.cache(_closing_over(1)),), (functools.cache(_closing_over(2)),)),
    "one more argument": ((1,), (1, None)),
    # ...two pokes, and ONE whose bytes spell the first's, then the second's address and length, then the second's:
    "where one poke ends and the next begins": (({0x100: b"\x01", 0x200: b"\x02"},),
                                               ({0x100: b"\x01" + struct.pack(">q", 0x200) + b"\x02"},)),
    "how long one poke is": (({0x100: b"\x01", 0x101: b"\x02"},), ({0x100: b"\x01\x02"},)),
    # ...pokes that OVERLAP are laid one over the other in the dict's own order, and that order is then the image:
    "the order two overlapping pokes are laid in": (({0x100: b"\x01\x02\x03", 0x101: b"\xff"},),
                                                    ({0x101: b"\xff", 0x100: b"\x01\x02\x03"},)),
    "the order two overlapping pokes of mutable bytes are laid in": (
        ({0x100: bytearray(b"\x01\x02\x03"), 0x101: bytearray(b"\xff")},),
        ({0x101: bytearray(b"\xff"), 0x100: bytearray(b"\x01\x02\x03")},)),
    "what an object says it is asked about": ((_Schedule({0: "a key"}, counted=0),), (_Schedule({0: "a press"}, counted=0),)),
}


@pytest.mark.parametrize("one, the_other", CHANGED_INPUTS.values(), ids=CHANGED_INPUTS)
def test_a_changed_input_is_another_question(one, the_other):
    """THE RED for an answer kept by too little of its input: each pair differs in one thing, and each is derived."""
    assert derived.fingerprint(one) != derived.fingerprint(the_other)
    asked, made = _counted()
    asked(*one), asked(*the_other)
    assert len(made) == 2
    asked(*one), asked(*the_other)
    assert len(made) == 2, "...and each is served to itself after"


def test_a_named_argument_is_not_the_positional_one_and_another_name_is_another_question():
    asked, made = _counted()
    asked(1), asked(by=1), asked(of=1)
    assert len(made) == 3


def test_equal_inputs_made_apart_are_one_question():
    """...and the other direction: content, not identity. Two closures of one `def` over equal values, two dicts built
    in another order, a bytearray and its bytes are the same argument."""
    for one, the_other in (((_closing_over(1),), (_closing_over(1),)),
                           (({"a": 1, "b": 2},), ({"b": 2, "a": 1},)),
                           (({2: b"\x02", 1: b"\x01"},), ({1: b"\x01", 2: b"\x02"},)),
                           ((bytearray(b"\x01"),), (bytearray(b"\x01"),)),
                           ((_Schedule({0: "a key"}, counted=0),), (_Schedule({0: "a key"}, counted=7),)),
                           ((Shape("A:\\", _closing_over(b"x")),), (Shape("A:\\", _closing_over(b"x")),))):
        assert derived.fingerprint(one) == derived.fingerprint(the_other)


def test_overlapping_pokes_are_read_as_the_image_they_make_laid_in_their_own_order():
    """THE RED for pokes read sorted by address: `make_image` lays a machine's runs in the DICT's order, so two dicts
    of the same overlapping runs in another order are two images — and were one key: the second machine was served
    the first's derivation (measured: a kept deriver answered `$ff $ff` where the images hold `$ff` and `$02`)."""
    over, under = {0x60000: b"\x01\x02\x03", 0x60001: b"\xff"}, {0x60001: b"\xff", 0x60000: b"\x01\x02\x03"}
    assert make_image(over)[0x60001] == 0xFF and make_image(under)[0x60001] == 0x02, "the premise: two images"
    byte_at = derived.kept(lambda pokes: make_image(pokes)[0x60001])
    assert (byte_at(over), byte_at(under), byte_at(over)) == (0xFF, 0x02, 0xFF)


def test_a_function_that_reaches_itself_through_its_closure_is_read_once():
    def again():
        return again
    assert derived.fingerprint(again) == derived.fingerprint(again)


class _Opaque:
    pass


@pytest.mark.parametrize("unreadable", (_Opaque(), object(), harness, iter(())), ids=("an object", "object()", "a module", "an iterator"))
def test_an_argument_that_cannot_be_read_by_value_is_refused_by_name(unreadable):
    """An answer is never kept on the strength of an object nobody can read: the call fails, naming the kind."""
    asked, made = _counted()
    with pytest.raises(derived.Unreadable, match="cannot be read by value"):
        asked(unreadable)
    with pytest.raises(derived.Unreadable):
        asked({"inside": [unreadable]})
    assert not made and not derived.ROOT.exists()


def _derives(answer):
    def derive(value):
        return (answer, value)
    return derive


def test_two_deriving_functions_do_not_answer_for_each_other():
    """THE RED for an answer kept by its deriver's NAME: two functions of two names — and two closures of ONE `def`,
    two lambdas of one line, which have one name between them — each answer for themselves alone."""
    def one(value):
        return ("one", value)

    def the_other(value):
        return ("the other", value)
    assert derived.kept(one)(1) == ("one", 1) and derived.kept(the_other)(1) == ("the other", 1)
    assert derived.kept(one)(1) == ("one", 1)
    assert derived.kept(_derives("a"))(1) == ("a", 1) and derived.kept(_derives("b"))(1) == ("b", 1)
    first, second = derived.kept(lambda: "the first"), derived.kept(lambda: "the second")
    assert (first(), second(), first()) == ("the first", "the second", "the first")
    assert derived.kept(_derives("a"))(1) == ("a", 1), "...and an equal closure made again is the same deriver"


def test_a_changed_base_image_is_another_question():
    """THE RED for an answer kept without the snapshot it was derived over: under another base image
    (`harness.set_base_image` — another capture's, in the sweep that proves no row depends on an unreproducible byte)
    the derivation is made again; back under the first, the first's answer is served."""
    asked, made = _counted()
    asked("a machine")
    another = bytearray(BASE_IMAGE)
    another[addrs.ST_RAM_BYTES - 1] ^= 0xFF
    previous = harness.set_base_image(bytes(another))
    try:
        assert derived.base_key() != derived.fingerprint("anything") and len(made) == 1
        asked("a machine")
        assert len(made) == 2, "an answer derived over the snapshot was served over another image"
        asked("a machine")
        assert len(made) == 2
    finally:
        harness.set_base_image(previous)
    asked("a machine")
    assert len(made) == 2


# ---- the tree ----------------------------------------------------------------------------------------------------------
def _a_small_tree(root):
    for name, text in (("test/a.py", "A = 1\n"), ("test/b.py", "B = 2\n"), ("include/x.h", "#define X 1\n")):
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    return root


def _its_digest(root):
    files = [Path(path) for pattern in ("test/*.py", "include/*.h") for path in sorted(derived._matching(root, pattern))]
    return derived.digest_of_files(files, root)


def _a_byte_changed(root):
    (root / "test/a.py").write_text("A = 2\n")


def _a_comment_added(root):
    (root / "include/x.h").write_text("#define X 1\n/* said */\n")


def _a_file_added(root):
    (root / "test/c.py").write_text("")


def _a_file_removed(root):
    (root / "test/b.py").unlink()


def _a_file_renamed(root):
    (root / "test/b.py").rename(root / "test/z.py")


def _two_files_contents_swapped(root):
    one, the_other = (root / "test/a.py").read_text(), (root / "test/b.py").read_text()
    (root / "test/a.py").write_text(the_other)
    (root / "test/b.py").write_text(one)


def _bytes_moved_across_a_file_s_end(root):
    (root / "test/a.py").write_text("A = 1\nB")
    (root / "test/b.py").write_text(" = 2\n")


@pytest.mark.parametrize("change", (_a_byte_changed, _a_comment_added, _a_file_added, _a_file_removed, _a_file_renamed,
                                    _two_files_contents_swapped, _bytes_moved_across_a_file_s_end),
                         ids=lambda change: change.__name__.strip("_").replace("_", " "))
def test_any_change_to_a_file_of_the_tree_is_another_tree(tmp_path, change):
    """THE RED for a deriver changed under a kept answer: the tree's digest is every file's path and bytes."""
    root = _a_small_tree(tmp_path / "tree")
    before = _its_digest(root)
    assert _its_digest(root) == before
    change(root)
    assert _its_digest(root) != before


EVERY_KIND_OF_INPUT = ("test/derived.py", "test/aes_event.py", "test/test_aes_evinput.py", "bench/tier3.py",
                       "tools/addrs.py", "include/addrs.h", "include/aes/evwait.h", "src/aes/evwait.c",
                       "src/aes/switch.S", "atari/target.mk", "build/boot_ram.bin", "project.toml", "Makefile",
                       "../aes_map/linef_dis.py")
EVERY_KIND_OF_KIT_INPUT = ("harness.py", "rom_bench.py", "oracle/emu.py", "oracle/build/liboracle.so", "include/os.h",
                           "src/gem.c", "kit.mk", "../hatari/TOS102US.img", "../prg_dis.py", "../st_build.py",
                           "../hatari_headless.py")


def test_the_tree_is_every_file_a_derivation_could_read_or_be_made_by():
    """The real tree's inputs, held to a file of every kind: the deriving Python (this cache's own, the door's, a
    battery, the bench, a tool, the Line-F decoder `rom_data` imports), the headers and sources the constants and the
    libraries come from, the snapshot, the kit's harness and oracle (source and library), the workspace tools the kit
    and the capture import, the ROM — and the candidate this process loaded, which is read apart."""
    files = {str(path) for path in derived.input_files()}
    missing = [name for name in EVERY_KIND_OF_INPUT if os.path.normpath(derived.RECREATE / name) not in files]
    missing += [name for name in EVERY_KIND_OF_KIT_INPUT if os.path.normpath(derived.KIT / name) not in files]
    assert not missing, f"not in the tree's key: {missing}"
    assert derived._tree().files[-1] == derived._candidate() and derived._candidate().is_file()


# What a process may have imported out of this repository BEFORE `derived` stamped the tree: the file that imports it
# first, and the kit's plugins a command line names (`-p recreate_kit.watchdog`, `-p recreate_kit.guarded_image`) —
# none of which derives. (A file changed between a process's beginning and that stamp is the other rule's: the
# process's own beginning.)
MAY_BE_LOADED_BEFORE = {derived.RECREATE / "test" / "conftest.py", derived.RECREATE / "test" / "derived.py",
                        derived.KIT / "__init__.py", derived.KIT / "watchdog.py", derived.KIT / "guarded_image.py"}


def test_every_module_this_process_imported_out_of_the_repository_is_a_file_of_the_key():
    """THE RED for a list of patterns TRUSTED to find every deriving file (four modules the registry imports were in
    no key: the Line-F decoder, the workspace tools behind the kit's loader and the capture): this process — a
    worker that has collected the whole suite — holds no module of this repository the key does not read; and none
    that derives was imported before the tree was stamped."""
    assert derived.unkeyed_modules() == []
    assert len(derived.repository_modules()) > 20, "the premise: this process imported the kit and a battery at least"
    assert {Path(file) for file in derived.LOADED_BEFORE} <= MAY_BE_LOADED_BEFORE, derived.LOADED_BEFORE


def test_a_script_read_from_standard_input_is_no_module_of_the_repository(monkeypatch):
    """`python - <<EOF` run from inside the tree is a `__main__` whose file is `<stdin>`: no file at all, and not a
    module the key fails to read (it once put every such script out of the cache, by the name `.../recreate/<stdin>`)."""
    script = types.ModuleType("a_script_read_from_standard_input")
    script.__file__ = "<stdin>"
    monkeypatch.setitem(sys.modules, script.__name__, script)
    assert derived.unkeyed_modules() == [] and not any("<stdin>" in file for file in derived.repository_modules())


BEGAN_BEFORE_ITS_FIRST_IMPORT_BY_AT_MOST_SECONDS = 600


def test_a_process_is_asked_when_it_began_and_a_child_began_after_its_parent_spawned_it():
    """`_began_ns` is the kernel's own record of THIS process: before this module was imported, and — asked in a
    fresh interpreter — between the moments its parent spawned it and reaped it."""
    assert derived._BEGAN_NS is not None and derived._BEGAN_NS == derived._began_ns()
    spawned = time.time_ns()
    child = subprocess.run([sys.executable, "-c", "import derived; print(derived._BEGAN_NS)"], capture_output=True,
                           text=True, cwd=derived.RECREATE / "test", check=True)
    assert spawned - derived._NS_PER_MICROSECOND <= int(child.stdout) <= time.time_ns()
    assert derived._BEGAN_NS < spawned


A_CLOCK_S_GRAIN_SECONDS = 0.002         # a file's dates and `time.time_ns` are apart by more than either's grain


@pytest.fixture
def a_tree(tmp_path, monkeypatch):
    """`a_tree()`: a `_Tree` over a small tree of the test's own (`a_tree.root`) and a candidate of its own
    (`a_tree.candidate`), of a process that BEGINS now and finds the tree as it is now — `found=` (`a_tree.found()`,
    taken earlier) and `began_ns=` for a process that found it, or began, before something the test then does."""
    monkeypatch.delenv(derived.HANDED_DOWN, raising=False)
    monkeypatch.setattr(derived, "FEWEST_INPUTS", 1)
    root = _a_small_tree(tmp_path / "tree")
    candidate = tmp_path / "lib.so"
    candidate.write_bytes(b"the candidate")

    def listing():
        return [Path(path) for path in sorted(derived._matching(root, "test/*.py"))]

    def found():
        return listing(), derived._stamps(listing())

    def now():
        time.sleep(A_CLOCK_S_GRAIN_SECONDS)
        try:
            return time.time_ns()
        finally:
            time.sleep(A_CLOCK_S_GRAIN_SECONDS)

    def made(found=None, began_ns=None):
        began_ns = now() if began_ns is None else began_ns
        return derived._Tree(listing, found or made.found(), began_ns, candidate, root)
    made.root, made.candidate, made.found, made.now = root, candidate, found, now
    return made


def _in_use(tree, monkeypatch):
    """`tree` made this process's, for the kept derivations a test asks."""
    monkeypatch.setattr(derived, "_tree", lambda: tree)
    return tree


def test_the_candidate_this_process_loaded_is_part_of_its_tree(a_tree, monkeypatch):
    before = a_tree().key
    monkeypatch.delenv(derived.HANDED_DOWN)
    a_tree.candidate.write_bytes(b"the candidate, rebuilt")
    assert a_tree().key not in (None, before)


def test_a_child_takes_its_parent_s_key_only_while_every_file_is_as_the_parent_found_it(a_tree, monkeypatch):
    """A process hands its key down with the record of its files' sizes and dates (HANDED_DOWN); a child whose own
    record is that one takes the key without reading the tree — and one that finds a file changed since reads it for
    itself. RED: a child that trusted the handed key would look its answers up in the tree its PARENT read."""
    read = []
    digest_of_files = derived.digest_of_files
    monkeypatch.setattr(derived, "digest_of_files", lambda *files: read.append(files) or digest_of_files(*files))
    parent = a_tree()
    assert len(read) == 1 and os.environ[derived.HANDED_DOWN].startswith(parent.key + ":")
    assert a_tree().key == parent.key and len(read) == 1, "an unchanged tree was read again by the child"
    _a_byte_changed(a_tree.root)
    child = a_tree()
    assert child.key not in (None, parent.key) and len(read) == 2
    assert os.environ[derived.HANDED_DOWN].startswith(child.key + ":"), "...and hands on its own from there"


def test_a_child_under_another_interpreter_reads_the_tree_for_itself_and_its_key_is_its_own(a_tree, monkeypatch):
    """The interpreter is part of the key — its version, and whether it runs its `assert`s (a deriver's vets are
    asserts: under `-O` it would keep what a plain run refuses) — and so part of what a child's trust compares."""
    parent = a_tree()
    monkeypatch.setattr(sys, "flags", types.SimpleNamespace(optimize=1))
    assert a_tree().key not in (None, parent.key)
    monkeypatch.undo()
    monkeypatch.setattr(derived, "FEWEST_INPUTS", 1)
    monkeypatch.setattr(sys, "version", sys.version + " (another build)")
    assert a_tree().key not in (None, parent.key)


def _nothing_kept_or_served():
    asked, made = _counted()
    asked("a question"), asked("a question")
    return len(made) == 2 and _kept_files() == [] and derived.switched_off()


def test_a_file_changed_after_the_process_began_puts_the_cache_out_of_use_for_it(a_tree, monkeypatch, capsys):
    """THE RED FOR A KEY THAT NAMES A TREE THE PROCESS IS NOT MADE OF. The key was made — and the files stamped — at
    the first kept question, 0.6 s into a worker's life with 43 modules imported: a file edited in between was keyed
    as the NEW tree by a process running the OLD module, and what it kept was served to every later process of the
    edited tree (measured, two processes: the pre-edit helper's `$30e0` served where the tree derives `$30e1`). A
    process a file changed under SINCE IT BEGAN — whenever it reads the tree — keeps nothing and is served nothing."""
    began = a_tree.now()
    _a_byte_changed(a_tree.root)                    # another agent's edit: after this process read its modules...
    tree = _in_use(a_tree(began_ns=began), monkeypatch)   # ...and before it asks its first kept question
    assert tree.key is None and "test/a.py changed after this process began" in tree.moved
    assert _nothing_kept_or_served()
    assert capsys.readouterr().err.count("changed after this process began — this process keeps and reads nothing") == 1


def test_a_changed_candidate_or_an_unknown_beginning_puts_the_cache_out_of_use_too(a_tree, monkeypatch):
    """...the library the process loaded is a file of its tree like any other (rebuilt after the process began: the
    one it dlopened may be either); and a process that cannot be asked when it began is trusted with nothing."""
    began = a_tree.now()
    a_tree.candidate.write_bytes(b"the candidate, rebuilt")
    assert "lib.so changed after this process began" in a_tree(began_ns=began).moved
    monkeypatch.setattr(derived, "_BEGAN_NS", None)
    unknown = _in_use(derived._Tree(lambda: a_tree.found()[0], a_tree.found(), derived._BEGAN_NS, a_tree.candidate,
                                    a_tree.root), monkeypatch)
    assert unknown.key is None and "cannot be asked when it began" in unknown.moved
    assert _nothing_kept_or_served()


def test_a_file_changed_between_the_stamps_and_the_key_puts_the_cache_out_of_use(a_tree, monkeypatch):
    """The files are stamped as the process finds them, when `derived` is imported — first; the key's BYTES are read
    at the first question. A file that is no longer what its stamp says by then: no key (held apart from the rule
    above by a process that "began" after the edit — the stamps alone must see it). An added file, a removed one."""
    for change, said in ((_a_byte_changed, "test/a.py changed under this process"),
                         (_a_file_added, "test/c.py was added to the tree, or left it"),
                         (_a_file_removed, "test/b.py was added to the tree, or left it")):
        found = a_tree.found()
        change(a_tree.root)
        tree = a_tree(found=found)
        assert tree.key is None and said in tree.moved, tree.moved
        _a_small_tree(a_tree.root)
        (a_tree.root / "test/c.py").unlink(missing_ok=True)
    assert a_tree().key is not None, "the tree put back is a tree again"


def test_a_key_handed_down_is_not_taken_over_files_that_changed_since_they_were_stamped(a_tree):
    """...and the same with a key HANDED DOWN that fits the stamps: a process stamps the tree as it imports this
    module and asks its first question later — if a file changed in between, its stamps are still its parent's,
    the handed key still "fits", and the key would be taken for a tree the process no longer reads. The stamps are
    asked again before any key is."""
    found = a_tree.found()
    parent = a_tree(found=found)
    assert parent.key and os.environ[derived.HANDED_DOWN].startswith(parent.key + ":")
    _a_byte_changed(a_tree.root)
    child = a_tree(found=found)
    assert child.key is None and "test/a.py changed under this process" in child.moved


def test_a_file_that_changes_while_the_key_s_bytes_are_read_leaves_no_key(a_tree, monkeypatch):
    """The key is the digest of bytes read AFTER the stamps were taken: a file that changes while they are read is
    half one tree's and half another's — the stamps are asked once more after the read, and there is no key."""
    digest_of_files = derived.digest_of_files

    def changed_under_the_read(*files):
        digest = digest_of_files(*files)
        _a_byte_changed(a_tree.root)
        return digest
    monkeypatch.setattr(derived, "digest_of_files", changed_under_the_read)
    tree = a_tree()
    assert tree.key is None and "test/a.py changed under this process" in tree.moved
    assert derived.HANDED_DOWN not in os.environ, "a key no tree has was handed down"


def _edited_with_its_date_put_back(path):
    """One byte of `path` changed — its size the same — and its modification date set back to what it was."""
    before = os.stat(path)
    path.write_text(path.read_text().replace("1", "2"))
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert os.stat(path).st_mtime_ns == before.st_mtime_ns and os.stat(path).st_size == before.st_size


def test_an_edit_whose_modification_date_was_put_back_is_still_seen(a_tree):
    """A tool that restores a file's date after editing it (a sweep that does not want `make` to rebuild) leaves its
    size and modification date as they were: the INODE's date moved with the write, and no `utime` sets that back.
    Both rules read it: changed since the process began, and changed since it was stamped."""
    began = a_tree.now()
    _edited_with_its_date_put_back(a_tree.root / "test/a.py")
    assert "test/a.py changed after this process began" in a_tree(began_ns=began).moved
    found = a_tree.found()
    _edited_with_its_date_put_back(a_tree.root / "test/b.py")
    assert "test/b.py changed under this process" in a_tree(found=found).moved


def test_a_tree_edited_under_a_process_stops_it_keeping_and_reading(a_tree, monkeypatch, capsys):
    """THE RED for a process that is half one tree and half another (modules imported before an edit, a header parsed
    after it): from the first write after any input file changed, it keeps nothing and is served nothing — said
    once — and what it kept before stays where the key of the tree that derived it names."""
    tree = _in_use(a_tree(), monkeypatch)
    asked, made = _counted()
    asked("before the edit")
    kept_before = _kept_files()
    assert len(kept_before) == 1 and tree.still()
    _a_byte_changed(a_tree.root)
    asked("after the edit"), asked("after the edit"), asked("before the edit")
    assert len(made) == 4, "an answer was served, or kept, by a process whose tree had changed under it"
    assert _kept_files() == kept_before and derived.switched_off()
    assert capsys.readouterr().err.count("changed under this process — this process keeps and reads nothing more") == 1


def _a_module_read_from(file):
    module = types.ModuleType("a_module_of_the_tree_imported_late")
    module.__file__ = str(file)
    return module


def test_a_process_whose_tree_was_edited_is_served_nothing_more_though_it_writes_nothing(a_tree, monkeypatch):
    """THE RED for "reads nothing more" held by WRITES alone (measured: a helper edited under a warm process and
    imported after — 20 asked, 20 served out of the tree before the edit): a READ asks too. At once where a module
    was imported since the tree was last asked — the edited file's — and within STILL_ASKED_EVERY_SECONDS where none
    was. And a process nothing changed under goes on being served."""
    _in_use(a_tree(), monkeypatch)
    asked, made = _counted()
    asked("a question"), asked("a question")
    monkeypatch.setattr(derived, "STILL_ASKED_EVERY_SECONDS", 0)
    asked("a question")
    assert len(made) == 1, "the premise: an unchanged tree's answer is served, however often the tree is asked"

    monkeypatch.setattr(derived, "STILL_ASKED_EVERY_SECONDS", 3600)
    _a_byte_changed(a_tree.root)
    monkeypatch.setitem(sys.modules, "a_module_of_the_tree_imported_late", _a_module_read_from(a_tree.root / "test/a.py"))
    asked("a question")
    assert len(made) == 2 and "test/a.py changed under this process, and was imported after" in derived._tree().moved

    _a_small_tree(a_tree.root)
    monkeypatch.delitem(sys.modules, "a_module_of_the_tree_imported_late")
    _in_use(a_tree(), monkeypatch)
    asked("another question"), asked("another question")
    _a_byte_changed(a_tree.root)
    asked("another question")
    assert len(made) == 3, "the premise: inside its interval, with no module imported, the last asking stands"
    monkeypatch.setattr(derived, "STILL_ASKED_EVERY_SECONDS", 0)
    asked("another question")
    assert len(made) == 4 and "test/a.py changed under this process" in derived._tree().moved


def test_a_module_the_key_does_not_read_puts_the_cache_out_of_use_for_the_process_that_imports_it(a_tree, monkeypatch):
    """...and a module of the repository that is NO file of the key (the patterns missed it, as they missed four): the
    process that imports it derives with code no key would notice an edit of — out, by the module's name. Before
    the key is made, or after."""
    unlisted = a_tree.root / "tools" / "unlisted.py"
    unlisted.parent.mkdir()
    unlisted.write_text("")
    tree = _in_use(a_tree(), monkeypatch)
    asked, made = _counted()
    asked("a question"), asked("a question")
    assert len(made) == 1 and not tree.moved
    monkeypatch.setitem(sys.modules, "a_module_of_the_tree_imported_late", _a_module_read_from(unlisted))
    asked("a question")
    assert len(made) == 2 and "tools/unlisted.py, which the tree's key does not read" in tree.moved
    assert "tools/unlisted.py, which the tree's key does not read" in a_tree().moved


def test_a_digest_s_parts_are_kept_apart():
    """Every key is a digest of PARTS — a file's path and its bytes, a tuple's members — and two lists of parts that
    spell the same bytes run together are two questions: each part is counted before it is read."""
    assert derived._digest(b"ab", b"c") != derived._digest(b"a", b"bc") != derived._digest(b"abc")
    assert derived._digest(b"", b"a") != derived._digest(b"a", b"") and derived._digest(b"a") == derived._digest(b"a")
    assert derived.fingerprint(("ab", "c")) != derived.fingerprint(("a", "bc"))


# ---- the files ---------------------------------------------------------------------------------------------------------
def test_an_answer_is_written_beside_its_place_and_renamed_into_it_never_written_in_place(monkeypatch):
    """HOW an answer reaches its file, which is what "whole or not at all" rests on: every byte is written to a
    scratch file of this process's own beside the answer's place, and the answer appears there by ONE rename. A
    writer that wrote into the place itself would show another process its first half."""
    written, renamed = [], []
    write_bytes, replace = Path.write_bytes, os.replace
    monkeypatch.setattr(Path, "write_bytes", lambda path, data: written.append(path) or write_bytes(path, data))
    monkeypatch.setattr(os, "replace", lambda scratch, place: renamed.append((Path(scratch), Path(place))) or replace(scratch, place))
    asked, _made = _counted()
    asked("a question")
    kept_at, = _kept_files()
    assert renamed == [(written[0], kept_at)] and len(written) == 1
    assert written[0].parent == kept_at.parent and written[0].suffix == ".part" and str(os.getpid()) in written[0].name


def test_a_write_that_fails_leaves_no_answer_and_no_scratch(monkeypatch):
    """...and a rename that fails (a disk that filled) leaves NOTHING: no answer, and no scratch file for the next
    process to step over — the derivation's own answer is still handed to the caller that made it? No: the failure
    is the caller's to see."""
    def failing(_scratch, _place):
        raise OSError("no space left on device")
    monkeypatch.setattr(os, "replace", failing)
    asked, made = _counted()
    with pytest.raises(OSError, match="no space left"):
        asked("a question")
    assert len(made) == 1 and _kept_files() == []


def test_a_kept_file_with_any_one_bit_flipped_is_no_answer():
    """THE RED for a kept file trusted to be what was written (a small one had no check: of 300 one-bit flips, 57
    loaded as ANOTHER answer and were served): every file carries the digest of what it holds, and no flip of any
    bit of a small plain answer's file — header, digest or pickle — loads."""
    asked, made = _counted()
    first = asked("a question")
    kept_at, = _kept_files()
    whole = kept_at.read_bytes()
    assert whole[:1] == derived.PLAIN and derived._loaded(whole) == first
    for bit in range(len(whole) * 8):
        flipped = bytearray(whole)
        flipped[bit // 8] ^= 1 << (bit % 8)
        kept_at.write_bytes(flipped)
        assert derived._read(kept_at) == (False, None), f"bit {bit} flipped, and the file was served"
    assert asked("a question") == {"made": 2}, "...and the derivation is made again"


def test_a_kept_file_that_does_not_load_is_no_answer_and_is_replaced():
    asked, made = _counted()
    first = asked("a question")
    kept_at, = _kept_files()
    whole = kept_at.read_bytes()
    assert derived._loaded(whole) == first
    for nth, not_an_answer in enumerate((b"", whole[:-3], whole[1:], b"not a kept answer at all"), start=2):
        kept_at.write_bytes(not_an_answer)
        again = asked("a question")
        assert again == {"made": nth} and derived._loaded(kept_at.read_bytes()) == again
    assert len(made) == 5


WRITERS, ANSWERS_EACH = 8, 40
A_LARGE_ANSWER = bytes(range(256)) * 4096       # a megabyte: a write another process could find half made


def _large(nth):
    time.sleep(0.001)
    return nth, A_LARGE_ANSWER


def test_processes_that_derive_the_same_things_at_once_leave_whole_answers_and_no_scratch():
    """UNDER XDIST every worker asks the same questions at the same moment: each writes its answer whole under a name
    of its own and renames it into place, so no reader ever loads half an answer and nothing but answers is left."""
    asked = derived.kept(_large)
    children = []
    for _writer in range(WRITERS):
        pid = os.fork()
        if pid == 0:
            status = 1
            try:
                status = 0 if all(asked(nth) == (nth, A_LARGE_ANSWER) for nth in range(ANSWERS_EACH)) else 2
            finally:
                os._exit(status)
        children.append(pid)
    assert [os.waitstatus_to_exitcode(os.waitpid(pid, 0)[1]) for pid in children] == [0] * WRITERS
    kept_at = _kept_files()
    assert len(kept_at) == ANSWERS_EACH and {path.suffix for path in kept_at} == {".pickle"}
    assert sorted(derived._loaded(path.read_bytes())[0] for path in kept_at) == list(range(ANSWERS_EACH))
    assert all(path.read_bytes()[:1] == derived.PACKED for path in kept_at), "the premise: an answer this large is packed"


def test_a_large_answer_is_kept_packed_and_a_small_one_plain_and_each_comes_back_whole():
    large, small = derived.kept(lambda: A_LARGE_ANSWER), derived.kept(lambda: b"a few bytes")
    assert large() == A_LARGE_ANSWER and small() == b"a few bytes"
    stored = sorted((path.stat().st_size, path.read_bytes()[:1]) for path in _kept_files())
    assert [how for _size, how in stored] == [derived.PLAIN, derived.PACKED] and stored[1][0] < len(A_LARGE_ANSWER) // 10
    assert large() == A_LARGE_ANSWER and small() == b"a few bytes"


def test_a_test_that_takes_monkeypatch_is_served_nothing_from_disk(request):
    """`conftest.py`'s rule, held here: this file's own fixture switches the cache ON for its tests (it is what they
    test) — every other test that takes `monkeypatch` runs with it OFF, set by the suite's autouse fixture."""
    the_suite_s = "a_test_that_patches_derives_and_forks_for_itself"
    assert "monkeypatch" in request.fixturenames and the_suite_s in request.fixturenames
    assert request.fixturenames.index(the_suite_s) < request.fixturenames.index("a_cache_of_the_test_s_own")


def test_switched_off_nothing_is_read_and_nothing_written(monkeypatch):
    asked, made = _counted()
    asked("kept while on")
    monkeypatch.setenv(derived.DERIVED_OFF, "1")
    kept_before = _kept_files()
    asked("kept while on"), asked("asked while off"), asked("asked while off")
    assert len(made) == 4 and _kept_files() == kept_before


def test_nothing_is_kept_for_a_candidate_that_is_not_the_project_s_own_build(monkeypatch, tmp_path):
    """A mutation sweep's private library is a tree of its own per mutant: written once, never read. Nothing is kept
    for a process that loaded one."""
    monkeypatch.undo()
    monkeypatch.setattr(derived, "ROOT", tmp_path / "derived")
    monkeypatch.delenv(derived.DERIVED_OFF, raising=False)
    assert derived._candidate_is_the_project_s.__wrapped__() == (derived._candidate().parent == derived.RECREATE / "build")
    monkeypatch.setattr(derived, "_candidate_is_the_project_s", lambda: False)
    asked, made = _counted()
    asked("a question"), asked("a question")
    assert len(made) == 2 and not derived.ROOT.exists()


def test_a_tree_nobody_used_for_long_goes_when_a_process_first_writes_to_another(monkeypatch):
    stale, recent = derived.ROOT / ("0" * 40), derived.ROOT / ("1" * 40)
    for tree in (stale, recent):
        (tree / "ab").mkdir(parents=True)
        (tree / "ab" / "an answer.pickle").write_bytes(b"")
    long_ago = time.time() - derived.PRUNE_AFTER_SECONDS - 60
    os.utime(stale, (long_ago, long_ago))
    asked, _made = _counted()
    asked("a question")
    assert not stale.exists() and recent.exists() and (derived.ROOT / derived.tree_key()).exists()


def test_only_the_trees_most_lately_used_are_kept_however_fresh_the_others(monkeypatch):
    """Every edit of the tree is a tree: beside this process's, the TREES_KEPT - 1 most lately used stay and the rest
    go, though none is PRUNE_AFTER_SECONDS old."""
    now = time.time()
    others = [derived.ROOT / f"{nth:040x}" for nth in range(derived.TREES_KEPT + 3)]
    for nth, tree in enumerate(others):
        tree.mkdir(parents=True)
        os.utime(tree, (now - 100 * nth, now - 100 * nth))        # the first the most lately used
    asked, _made = _counted()
    asked("a question")
    kept = sorted(tree.name for tree in derived.ROOT.iterdir() if tree.name != derived.tree_key())
    assert kept == [tree.name for tree in others[:derived.TREES_KEPT - 1]]


# ---- a derivation in flight, claimed (`derived._served_or_claimed`) ------------------------------------------------------
A_DERIVATION_S_SECONDS = 0.5            # long enough that a process forked while it is made asks before it ends
ENDS_WITHIN_SECONDS = 30                # a fork that asks one question, on a machine three suites are running on
LOOKED_EVERY_SECONDS = 0.01             # ...and how often this file looks whether it has
NO_CLAIM_IS_STUCK_SECONDS = 3600        # CLAIM_STUCK_AFTER_SECONDS for a test in which a waiter must not rest on it
STUCK_AFTER_SECONDS = 1.0               # ...and for one in which it must
_HELD, _NOT_HELD, _RAISED = 0, 3, 4     # how a fork ends: what it was asked held, did not, or raised


@pytest.fixture
def forked():
    """`forked(holds)`: the pid of a fork of this process that calls `holds()` and ends with `_HELD` where it answers
    True. `forked.ended(pid)`: how it ended — None for one killed because it had not after ENDS_WITHIN_SECONDS (a
    waiter that waits for ever FAILS its test: it does not hang the run). `forked.killed(pid)`: killed, and reaped
    unless told not to (`forked.reaped(pid)`, later). A fork still out when the test ends is killed."""
    out = []

    def fork(holds):
        pid = os.fork()
        if pid == 0:
            status = _RAISED
            try:
                status = _HELD if holds() is True else _NOT_HELD
            finally:
                os._exit(status)
        out.append(pid)
        return pid

    def reaped(pid):
        out.remove(pid)
        return os.waitstatus_to_exitcode(os.waitpid(pid, 0)[1])

    def ended(pid):
        over = time.monotonic() + ENDS_WITHIN_SECONDS
        while True:
            done, status = os.waitpid(pid, os.WNOHANG)
            if done:
                out.remove(pid)
                return os.waitstatus_to_exitcode(status)
            if time.monotonic() >= over:
                killed(pid)
                return None
            time.sleep(LOOKED_EVERY_SECONDS)

    def killed(pid, and_reaped=True):
        os.kill(pid, signal.SIGKILL)
        return reaped(pid) if and_reaped else None
    fork.ended, fork.killed, fork.reaped = ended, killed, reaped
    yield fork
    for pid in list(out):
        killed(pid)


def _until(holds):
    """Wait until `holds()` — for ENDS_WITHIN_SECONDS at most."""
    over = time.monotonic() + ENDS_WITHIN_SECONDS
    while not holds():
        assert time.monotonic() < over, "what the test waited for never came"
        time.sleep(LOOKED_EVERY_SECONDS)


def _claims():
    return sorted(derived.ROOT.rglob(f"*{derived.CLAIM_SUFFIX}"))


def _said_in(log):
    """What the derivations that say so said in `log`, in order: `(the word, the pid, when)`."""
    lines = Path(log).read_text().splitlines() if os.path.exists(log) else []
    return [(word, int(pid), float(when)) for word, pid, when in map(str.split, lines)]


def _say(log, word):
    with open(log, "a") as said:
        said.write(f"{word} {os.getpid()} {time.monotonic()}\n")


def _made_slowly(log, seconds=0):
    """A derivation that says in `log` when it begins and when it ends, `seconds` apart."""
    _say(log, "begins")
    time.sleep(seconds)
    _say(log, "ends")
    return "made slowly", seconds


def _raising_slowly(log, seconds):
    _made_slowly(log, seconds)
    raise ValueError("what the derivation raises")


def _never_made_by_the_first_to_try(log):
    """A derivation the FIRST process to make it never ends (it is there to be killed); the next one's ends at once."""
    _say(log, "begins")
    if len(_said_in(log)) == 1:
        time.sleep(NO_CLAIM_IS_STUCK_SECONDS)
    return "made by the second to try"


def _the_claims_standing(_question):
    """A derivation that answers the claims standing while it is made: each one's name, and the maker it names."""
    return [(claim.name, claim.read_bytes()) for claim in _claims()]


def _place_of(asked, *arguments):
    """Where the answer of `asked(*arguments)` is kept, asked now."""
    return derived._path_of(derived.key_of(asked.derive, arguments, {}))


def _a_claim_planted(asked, *arguments, maker):
    """Another process's claim on `asked(*arguments)`, as if `maker` were making it: the claim's file."""
    claim = derived._claim_of(_place_of(asked, *arguments))
    claim.parent.mkdir(parents=True, exist_ok=True)
    claim.write_bytes(maker)
    return claim


def test_processes_that_ask_one_cold_question_at_once_make_it_once(forked, tmp_path):
    """THE RED for a cold tree's workers each making what they all import (measured: ten processes, one battery,
    72 CPU-seconds for 7 of derivations): the first to ask CLAIMS the derivation, the others wait for its answer —
    made once, answered to each, and nothing left beside the answer."""
    asked, log, askers = derived.kept(_made_slowly), str(tmp_path / "made"), 6
    answered = [forked(lambda: asked(log, A_DERIVATION_S_SECONDS) == ("made slowly", A_DERIVATION_S_SECONDS))
                for _asker in range(askers)]
    assert [forked.ended(pid) for pid in answered] == [_HELD] * askers
    assert [word for word, _pid, _when in _said_in(log)] == ["begins", "ends"], "made by more than one of them"
    assert [path.suffix for path in _kept_files()] == [".pickle"], "a claim, or a claim's scratch file, was left"


def test_a_claim_stands_beside_the_answer_s_place_while_it_is_made_and_names_its_maker():
    """...a claim is a file beside the answer's place, there from before the derivation's first line to after its
    answer is written, and it holds its maker's pid and when the kernel says that process began."""
    standing = derived.kept(_the_claims_standing)("a question")
    kept_at, = _kept_files()
    assert standing == [(kept_at.with_suffix(derived.CLAIM_SUFFIX).name, f"{os.getpid()} {derived._began_ns()}".encode())]
    assert _claims() == [] and derived._CLAIMS_HELD == []


def test_a_claim_is_one_process_s_at_a_time():
    """THE CLAIM IS TAKEN BY ONE: taking it where it stands fails, whoever tries — it is there whole, naming its maker,
    or not there (linked into place: at no moment does it stand and name nobody) — and only its release frees it."""
    claim = derived._claim_of(derived.ROOT / "a tree" / "ab" / "a key.pickle")
    assert derived._claimed(claim) and claim.read_bytes() == derived._claimant()
    assert not derived._claimed(claim) and derived._CLAIMS_HELD == [claim]
    assert _kept_files() == [claim], "a scratch file was left beside the claim"
    derived._given_up(claim)
    assert _kept_files() == [] and derived._CLAIMS_HELD == [] and derived._claimed(claim)
    derived._given_up(claim)


def test_a_process_is_asked_when_another_began_and_one_that_is_no_more_did_not(forked):
    """What tells a claim's maker from a later process given its pid — and a maker that lives from one that ended:
    `_began_ns(pid)` is that process's own beginning (a fork's is not its parent's), and None once it ended, reaped
    or not."""
    spawned = time.time_ns()
    child = forked(lambda: time.sleep(NO_CLAIM_IS_STUCK_SECONDS))
    assert spawned - derived._NS_PER_MICROSECOND <= derived._began_ns(child) <= time.time_ns()
    assert derived._began_ns(child) != derived._began_ns() == derived._BEGAN_NS
    forked.killed(child, and_reaped=False)
    _until(lambda: derived._began_ns(child) is None)
    assert forked.reaped(child) == -signal.SIGKILL, "the premise: it ended, and was still to be reaped"
    assert derived._began_ns(child) is None


@pytest.mark.parametrize("and_reaped", (True, False), ids=("and reaped", "and not yet reaped"))
def test_a_maker_killed_mid_derivation_leaves_its_waiter_to_make_the_answer(forked, tmp_path, monkeypatch, and_reaped):
    """A worker killed while it makes an answer (the watchdog's exit, an out-of-memory kill) leaves its claim: the
    process waiting on it sees that the maker is NO MORE — though no time bound is near — takes the claim over, makes
    the answer and leaves nothing behind. A maker nobody reaped yet is no more either."""
    monkeypatch.setattr(derived, "CLAIM_STUCK_AFTER_SECONDS", NO_CLAIM_IS_STUCK_SECONDS)
    asked, log = derived.kept(_never_made_by_the_first_to_try), str(tmp_path / "made")
    maker = forked(lambda: asked(log) is None)
    _until(lambda: len(_said_in(log)) == 1 and _claims())
    waiter = forked(lambda: asked(log) == "made by the second to try")
    time.sleep(A_DERIVATION_S_SECONDS)
    assert len(_said_in(log)) == 1, "the premise: while the maker lives, the waiter waits and does not make it too"
    forked.killed(maker, and_reaped)
    assert forked.ended(waiter) == _HELD
    assert [pid for _word, pid, _when in _said_in(log)] == [maker, waiter]
    assert [path.suffix for path in _kept_files()] == [".pickle"] and asked(log) == "made by the second to try"


def _nobody(_forked):
    return b""


def _another_process_given_this_one_s_pid(_forked):
    return f"{os.getpid()} {derived._began_ns() - derived._NS_PER_MICROSECOND}".encode()


def _a_process_that_ended(forked):
    ended = forked(lambda: True)
    named = f"{ended} {derived._began_ns(ended)}".encode()
    assert forked.ended(ended) == _HELD
    return named


@pytest.mark.parametrize("maker", (_nobody, _another_process_given_this_one_s_pid, _a_process_that_ended),
                         ids=lambda maker: maker.__name__.strip("_").replace("_", " "))
def test_a_claim_whose_maker_is_no_more_is_taken_over_by_whoever_finds_it(forked, tmp_path, monkeypatch, maker):
    """...and a claim FOUND with no maker — a run killed days ago, its pid since given to another process (which
    began at another time), a file that names nobody — is not waited on at all."""
    monkeypatch.setattr(derived, "CLAIM_STUCK_AFTER_SECONDS", NO_CLAIM_IS_STUCK_SECONDS)
    asked, log = derived.kept(_made_slowly), str(tmp_path / "made")
    _a_claim_planted(asked, log, maker=maker(forked))
    assert forked.ended(forked(lambda: asked(log) == ("made slowly", 0))) == _HELD
    assert len(_said_in(log)) == 2 and [path.suffix for path in _kept_files()] == [".pickle"]


def _a_process_that_lives(forked):
    """A process that outlives the test's questions, as a claim names it."""
    alive = forked(lambda: time.sleep(NO_CLAIM_IS_STUCK_SECONDS))
    return f"{alive} {derived._began_ns(alive)}".encode()


def test_a_claim_that_stood_too_long_under_one_maker_is_taken_over_though_the_maker_lives(forked, tmp_path, monkeypatch):
    """A maker that lives and never answers (stopped, spinning in the oracle) holds its waiters for
    CLAIM_STUCK_AFTER_SECONDS and no longer: the waiter then makes the answer itself — and a claim that changed
    hands meanwhile is waited on for its NEW maker's whole time (ten waiters do not all take over from the first of
    them that did)."""
    monkeypatch.setattr(derived, "CLAIM_STUCK_AFTER_SECONDS", STUCK_AFTER_SECONDS)
    asked, log = derived.kept(_made_slowly), str(tmp_path / "made")
    first, second = _a_process_that_lives(forked), _a_process_that_lives(forked)
    claim = _a_claim_planted(asked, log, maker=first)
    waiter = forked(lambda: asked(log) == ("made slowly", 0))
    time.sleep(STUCK_AFTER_SECONDS / 2)
    assert _said_in(log) == [] and claim.read_bytes() == first, "the premise: the waiter waits on a maker that lives"
    claim.write_bytes(second)
    changed_hands = time.monotonic()
    assert forked.ended(waiter) == _HELD
    (_begins, by, began), _ends = _said_in(log)
    assert by == waiter and began - changed_hands >= STUCK_AFTER_SECONDS, "the second maker was not given its own time"
    assert [path.suffix for path in _kept_files()] == [".pickle"]


def test_a_maker_whose_claim_was_taken_over_leaves_the_new_maker_s_standing():
    """...and the maker that was taken over from, when it ends at last, removes only a claim that is still its own."""
    another_s = b"1 1"
    asked = derived.kept(lambda: [claim.write_bytes(another_s) for claim in _claims()])
    assert asked() == [len(another_s)]
    assert [claim.read_bytes() for claim in _claims()] == [another_s] and derived._CLAIMS_HELD == []


def test_a_derivation_that_raises_leaves_no_claim_and_its_waiter_makes_it_and_meets_the_same_raise(forked, tmp_path):
    """A derivation that raises (a vet of its own, a ROM run that does not end) must not leave waiters waiting: its
    claim goes as the raise passes, nothing is kept, and the process that waited makes the derivation in its turn —
    AFTER the first, not beside it — and is raised the same."""
    asked, log = derived.kept(_raising_slowly), str(tmp_path / "made")

    def is_raised_it():
        with pytest.raises(ValueError, match="what the derivation raises"):
            asked(log, A_DERIVATION_S_SECONDS)
        return True
    maker = forked(is_raised_it)
    _until(lambda: _said_in(log))
    waiter = forked(is_raised_it)
    assert [forked.ended(maker), forked.ended(waiter)] == [_HELD, _HELD]
    assert [(word, pid) for word, pid, _when in _said_in(log)] == [("begins", maker), ("ends", maker), ("begins", waiter),
                                                                  ("ends", waiter)]
    assert _kept_files() == []


SEVERAL_ASKERS = 6
NOT_IN_TURN_WITHIN = 0.67               # of the time the waiters take ONE AFTER ANOTHER: side by side is a sixth of it


def test_a_derivation_that_raises_is_made_by_its_waiters_side_by_side_not_one_after_another(forked, tmp_path):
    """RED before a waiter told a claim GIVEN UP from one it took over: ten askers of a derivation that raises took
    the claim IN TURN, each making it — and raising — while the rest waited on it (5.4 s where ten unclaimed
    processes raise in 0.5 s). The claim a waiter rested on went with no answer left: every such waiter makes the
    derivation itself, unclaimed, at once — after the first maker, beside one another."""
    asked, log = derived.kept(_raising_slowly), str(tmp_path / "made")

    def is_raised_it():
        with pytest.raises(ValueError, match="what the derivation raises"):
            asked(log, A_DERIVATION_S_SECONDS)
        return True
    maker = forked(is_raised_it)
    _until(lambda: _said_in(log) and _claims())
    waiters = [forked(is_raised_it) for _asker in range(SEVERAL_ASKERS)]
    assert [forked.ended(pid) for pid in (maker, *waiters)] == [_HELD] * (1 + SEVERAL_ASKERS)
    said = _said_in(log)
    assert sorted(pid for word, pid, _when in said if word == "begins") == sorted((maker, *waiters)), "each raised its own"
    the_maker_ended = next(when for word, pid, when in said if (word, pid) == ("ends", maker))
    began = sorted(when for word, pid, when in said if word == "begins" and pid != maker)
    ended = sorted(when for word, pid, when in said if word == "ends" and pid != maker)
    assert began[0] >= the_maker_ended, "the premise: they waited for the first maker"
    one_after_another = SEVERAL_ASKERS * A_DERIVATION_S_SECONDS
    assert ended[-1] - the_maker_ended < one_after_another * NOT_IN_TURN_WITHIN, (
        f"the {SEVERAL_ASKERS} waiters took {ended[-1] - the_maker_ended:.2f} s to raise: in turn is {one_after_another} s")
    assert _kept_files() == []


def _stopped_while_it_makes(log):
    """A derivation whose maker STOPS itself as it makes it (as a `kill -STOP` of a sweep does), and answers once
    continued."""
    _say(log, "begins")
    if len(_said_in(log)) == 1:
        os.kill(os.getpid(), signal.SIGSTOP)
    return "made"


def test_a_stopped_maker_holds_no_waiter_and_its_claim_is_taken_over_at_once(forked, tmp_path):
    """RED: a maker that is alive and STOPPED held every waiter for the whole CLAIM_STUCK_AFTER_SECONDS (44 s each,
    polling — a bound no test ran at its own value). A stopped process makes nothing until it is continued: its
    claim is taken over as soon as a waiter looks, the bound left as it stands. Continued, the first maker ends
    as any maker taken over from: its answer the same bytes, the new maker's claim not its own to remove."""
    assert derived.CLAIM_STUCK_AFTER_SECONDS > ENDS_WITHIN_SECONDS, "the premise: the bound is NOT what ends this wait"
    asked, log = derived.kept(_stopped_while_it_makes), str(tmp_path / "made")
    maker = forked(lambda: asked(log) == "made")
    _until(lambda: _claims() and derived._is_stopped(maker))
    assert derived._began_ns(maker) is not None and not derived._is_no_more(_claims()[0].read_bytes())
    began = time.monotonic()
    waiter = forked(lambda: asked(log) == "made")
    assert forked.ended(waiter) == _HELD and time.monotonic() - began < ENDS_WITHIN_SECONDS
    assert [pid for _word, pid, _when in _said_in(log)] == [maker, waiter]
    os.kill(maker, signal.SIGCONT)
    assert forked.ended(maker) == _HELD
    assert [path.suffix for path in _kept_files()] == [".pickle"] and asked(log) == "made"
    assert not derived._is_stopped(os.getpid()) and not derived._is_stopped(maker), "a process that ended is not stopped"


class _AClock:
    """`time`, for `derived`: a clock that only a sleep moves — so a wait of forty seconds is run in none."""

    def __init__(self):
        self.now, self.rests = 1000.0, []

    def monotonic(self):
        return self.now

    def monotonic_ns(self):
        return int(self.now * 10 ** 9)

    def sleep(self, seconds):
        self.rests.append(seconds)
        self.now += seconds

    def __getattr__(self, name):        # whatever else `derived` asks of `time` (a file's dates): the real one's
        return getattr(time, name)


def test_a_waiter_rests_longer_at_every_look_and_takes_over_at_the_bound_itself(forked, tmp_path, monkeypatch):
    """THE BOUND AT ITS OWN VALUE, and the rests on the way to it (every other case patches the bound; a waiter that
    did not rest at all, or took over at half the time, or never, passed them): under a maker that lives and never
    answers the waiter's rests GROW FROM ITS FIRST LOOK — CLAIM_ASKED_EVERY_SECONDS, then twice the last each time,
    up to CLAIM_ASKED_AT_LEAST_EVERY_SECONDS and no further — and it takes the claim over when
    CLAIM_STUCK_AFTER_SECONDS have gone under that ONE maker, not a rest before. (RED while the longer rest began
    after a whole second of one question: no question of a measured cold import waits that long — the back-off the
    constant pinned never engaged.)"""
    assert derived.CLAIM_STUCK_AFTER_SECONDS == derived.SLOWED_AT_MOST_TIMES * derived.LONGEST_DERIVATION_SECONDS == 44
    asked, made = _counted(steady="made by the waiter")
    _a_claim_planted(asked, "a question", maker=_a_process_that_lives(forked))
    clock = _AClock()
    monkeypatch.setattr(derived, "time", clock)
    assert asked("a question") == "made by the waiter" and len(made) == 1
    waited = sum(clock.rests)
    shortest, longest = derived.CLAIM_ASKED_EVERY_SECONDS, derived.CLAIM_ASKED_AT_LEAST_EVERY_SECONDS
    assert derived.CLAIM_STUCK_AFTER_SECONDS <= waited < derived.CLAIM_STUCK_AFTER_SECONDS + 2 * longest
    growing = [rest for rest in clock.rests if rest < longest]
    assert growing == [shortest * derived.CLAIM_REST_GROWS_TIMES ** look for look in range(len(growing))] == [0.005, 0.01, 0.02, 0.04]
    assert clock.rests == growing + [longest] * (len(clock.rests) - len(growing)), "growing rests first, then the bound"
    # ...so a question answered within THE_MEAN_WAIT_SECONDS is looked at half as often as at a steady 5 ms.
    looks = next(look for look in range(len(clock.rests)) if sum(clock.rests[:look]) >= THE_MEAN_WAIT_SECONDS)
    assert looks <= THE_MEAN_WAIT_SECONDS / shortest / 2
    assert _claims() == [] and derived._CLAIMS_HELD == []


THE_MEAN_WAIT_SECONDS = 0.06            # of one question of ten cold importers side by side, measured


A_CLAIM_THAT_NAMES_NOBODY = {
    "thousands of digits": b"1" * 5000 + b" " + b"2" * 5000,
    "a pid too long for any process": b"1" * 11 + b" 5",
    "no time": b"12345",
    "words": b"a maker",
    "negative numbers": b"-5 -6",
}


@pytest.mark.parametrize("named", A_CLAIM_THAT_NAMES_NOBODY.values(), ids=A_CLAIM_THAT_NAMES_NOBODY)
def test_a_claim_that_names_nothing_readable_has_no_maker_and_raises_nothing(named):
    """RED: a claim of five thousand digits raised ValueError out of every asker (an `int` of a string that long is
    refused by the interpreter itself). A claim names its maker by two SHORT numbers or it names nobody: it is
    removed by whoever finds it, and the asker makes its answer."""
    assert derived._named_by(named) is None and derived._is_no_more(named) and derived._makes_nothing_now(named)
    asked, made = _counted(steady="made")
    _a_claim_planted(asked, "a question", maker=named)
    assert asked("a question") == "made" and len(made) == 1 and _claims() == []


def test_which_process_a_claim_names_is_its_pid_and_when_it_began_both(forked):
    """...and the two numbers are read BOTH WAYS: this very process at the time it began is a maker that lives; the
    same pid at another time is another process (the pid given again) — no more; another pid at this one's time, a
    process that is not there."""
    pid, began = os.getpid(), derived._began_ns()
    assert derived._named_by(f"{pid} {began}".encode()) == (pid, began)
    assert not derived._is_no_more(f"{pid} {began}".encode())
    assert derived._is_no_more(f"{pid} {began + 1}".encode()) and derived._is_no_more(f"{pid} {began - 1}".encode())
    gone = _a_process_that_ended(forked)
    assert derived._is_no_more(gone) and derived._makes_nothing_now(gone)


def test_a_claim_is_removed_only_while_it_names_the_maker_it_was_seen_to_name():
    """A waiter that takes a claim over removes the claim IT WATCHED: one another process has taken since — it names
    another maker — is that process's, and stays."""
    claim = derived.ROOT / "a tree" / "ab" / f"a key{derived.CLAIM_SUFFIX}"
    claim.parent.mkdir(parents=True)
    claim.write_bytes(b"1 1")
    derived._removed_while_it_names(claim, b"2 2")
    assert claim.read_bytes() == b"1 1"
    derived._removed_while_it_names(claim, b"1 1")
    assert not claim.exists()
    derived._removed_while_it_names(claim, b"1 1")      # gone already: nothing


def test_a_place_that_cannot_be_claimed_is_made_unclaimed_and_never_looked_at_for_ever(monkeypatch):
    """RED, two ways a claim's place can refuse every claim: a file system that makes no hard links (`os.link`
    raised out of the asker, where there were no claims the derivation was simply made) — and a place that READS as
    nobody's and still refuses the link (a dangling link left there): looked at again and again, no rest, no bound.
    Each is made unclaimed, as before there were claims, and kept."""
    asked, made = _counted(steady="made")

    def no_hard_links(_source, _link):
        raise OSError(45, "Operation not supported")
    link = derived.os.link
    monkeypatch.setattr(derived.os, "link", no_hard_links)
    assert asked("a question") == "made" and len(made) == 1 and derived._CLAIMS_HELD == []
    monkeypatch.setattr(derived.os, "link", link)       # (put back by hand: `undo` would undo this file's own cache too)
    claim = derived._claim_of(_place_of(asked, "another question"))
    assert derived.ROOT in claim.parents, "the premise: the test's own cache"
    claim.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(claim.with_name("nothing is here"), claim)
    assert derived._maker_of(claim) is None and derived._claimed(claim) is False, "the premise: nobody's, and not to be had"
    assert asked("another question") == "made" and len(made) == 2 and derived._CLAIMS_HELD == []
    assert asked("another question") == "made" and len(made) == 2, "...and kept: the next asker is served"


def test_a_claim_is_given_up_whatever_ends_the_derivation(monkeypatch):
    """The claim goes in a `finally`: a derivation ended by what is no `Exception` (the watchdog's KeyboardInterrupt,
    a SystemExit) leaves none standing for the next asker to wait on."""
    def interrupted():
        raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        derived.kept(interrupted)()
    assert _claims() == [] and derived._CLAIMS_HELD == []


def test_giving_one_claim_up_leaves_the_others_this_process_holds():
    """A derivation that asks another holds TWO claims while the inner one is made, and the inner one's release
    leaves the outer HELD — which is what keeps a process that holds a claim from ever waiting on another's."""
    inner, _made = _counted(steady="the inner answer")
    held_after_the_inner = []

    def outer():
        answer = inner("asked inside")
        held_after_the_inner.extend(derived._CLAIMS_HELD)
        return answer
    assert derived.kept(outer)() == "the inner answer"
    (still_held,) = held_after_the_inner
    assert still_held.suffix == derived.CLAIM_SUFFIX and derived._CLAIMS_HELD == [] and _claims() == []


def test_an_answer_a_process_waited_for_is_sampled_as_any_it_is_served(forked, monkeypatch):
    """What a waiter is served goes through everything a hit does — the sample too: made again and held equal where
    the sample chooses its key."""
    asked, made = _counted(steady="the answer")
    place = _place_of(asked, "a question")
    claim = _a_claim_planted(asked, "a question", maker=_a_process_that_lives(forked))
    rest = time.sleep

    def the_maker_writes_while_this_one_rests(seconds):
        place.write_bytes(derived._stored("the answer"))
        claim.unlink(missing_ok=True)
        rest(seconds)
    monkeypatch.setattr(derived.time, "sleep", the_maker_writes_while_this_one_rests)
    monkeypatch.setattr(derived, "_sampled", lambda _key: True)
    monkeypatch.setattr(derived, "SAMPLED", [])
    assert asked("a question") == "the answer"
    assert len(made) == 1 and len(derived.SAMPLED) == 1, "served by waiting, then made again once: the sample"


def test_an_answer_written_between_a_miss_and_the_claim_is_served_and_not_made_again(monkeypatch):
    """A process that finds no answer and then no claim may be looking a moment AFTER another wrote the one and
    removed the other: with the claim in hand it reads once more, and is served."""
    asked, made = _counted()
    claimed = derived._claimed

    def claimed_a_moment_late(claim):
        derived._write(_place_of(asked, "a question"), derived._stored("another process's answer"))
        return claimed(claim)
    monkeypatch.setattr(derived, "_claimed", claimed_a_moment_late)
    assert asked("a question") == "another process's answer" and made == []
    assert [path.suffix for path in _kept_files()] == [".pickle"] and derived._CLAIMS_HELD == []


def test_a_waiter_is_served_only_what_a_hit_would_be_served(forked, tmp_path, monkeypatch):
    """What appears at the answer's place while a process waits is read as a hit's is: a file whose digest is not of
    what it holds is no answer, though what it holds LOADS — the waiter goes on waiting, and makes the answer when
    the claim is its own."""
    monkeypatch.setattr(derived, "CLAIM_STUCK_AFTER_SECONDS", STUCK_AFTER_SECONDS)
    asked, log = derived.kept(_made_slowly), str(tmp_path / "made")
    _a_claim_planted(asked, log, maker=_a_process_that_lives(forked))
    whole = bytearray(derived._stored("not what the derivation answers"))
    whole[len(derived.PLAIN)] ^= 1                  # the first byte of its digest: the pickle after it is whole
    assert pickle.loads(whole[derived._HEADER_BYTES:]) == "not what the derivation answers"
    _place_of(asked, log).write_bytes(whole)
    assert forked.ended(forked(lambda: asked(log) == ("made slowly", 0))) == _HELD
    assert len(_said_in(log)) == 2 and [path.suffix for path in _kept_files()] == [".pickle"]
    assert asked(log) == ("made slowly", 0) and len(_said_in(log)) == 2


def test_a_waiter_the_cache_goes_out_of_use_for_stops_waiting_and_makes_its_answer_itself(forked, tmp_path, monkeypatch,
                                                                                         a_tree):
    """A tree edited under a process WHILE it waits: that process is served nothing more — not the answer it waits
    for either — so it stops waiting, makes what it was asked, keeps none of it, and leaves the claim to its maker."""
    monkeypatch.setattr(derived, "CLAIM_STUCK_AFTER_SECONDS", NO_CLAIM_IS_STUCK_SECONDS)
    monkeypatch.setattr(derived, "STILL_ASKED_EVERY_SECONDS", 0)
    _in_use(a_tree(), monkeypatch)
    asked, log = derived.kept(_made_slowly), str(tmp_path / "made")
    planted = _a_claim_planted(asked, log, maker=_a_process_that_lives(forked))
    waiter = forked(lambda: asked(log) == ("made slowly", 0))
    time.sleep(A_DERIVATION_S_SECONDS)
    assert _said_in(log) == [], "the premise: while its tree is the one it found, it waits"
    _a_byte_changed(a_tree.root)
    assert forked.ended(waiter) == _HELD
    assert len(_said_in(log)) == 2 and _kept_files() == [planted]


def test_a_process_that_holds_a_claim_claims_what_it_asks_in_turn_and_never_waits_for_another_s(forked, monkeypatch):
    """A derivation that asks another (a session's deliveries ask its run) claims that one too, where nobody has —
    and where another process HAS, it does not wait: it makes it. A process that waited while it held a claim could
    be waited on by the one it waits for; one that holds nothing can not."""
    monkeypatch.setattr(derived, "CLAIM_STUCK_AFTER_SECONDS", NO_CLAIM_IS_STUCK_SECONDS)
    inner = derived.kept(_the_claims_standing)
    outer = derived.kept(lambda question: inner(question))
    assert [maker for _claim, maker in outer("nobody's")] == [derived._claimant()] * 2 and _claims() == []

    another_s = _a_process_that_lives(forked)
    planted = _a_claim_planted(inner, "another's", maker=another_s)
    asker = forked(lambda: sorted(maker for _claim, maker in outer("another's")) == sorted([another_s, derived._claimant()]))
    assert forked.ended(asker) == _HELD, "it waited for the other's claim, or took it"
    assert _claims() == [planted] and planted.read_bytes() == another_s
    assert _place_of(inner, "another's").is_file(), "what it made unclaimed is kept all the same"


def _switched_off_in_the_environment(monkeypatch, _a_tree):
    monkeypatch.setenv(derived.DERIVED_OFF, "1")


def _a_candidate_that_is_not_the_project_s_build(monkeypatch, _a_tree):
    monkeypatch.setattr(derived, "_candidate_is_the_project_s", lambda: False)


def _a_served_answer_being_made_again(monkeypatch, _a_tree):
    monkeypatch.setattr(derived, "_MADE_AGAIN_NOW", ["a key"])


def _a_tree_edited_under_the_process(monkeypatch, a_tree):
    _a_byte_changed(a_tree.root)
    monkeypatch.setattr(derived, "STILL_ASKED_EVERY_SECONDS", 0)


@pytest.mark.parametrize("out_of_use", (_switched_off_in_the_environment, _a_candidate_that_is_not_the_project_s_build,
                                        _a_served_answer_being_made_again, _a_tree_edited_under_the_process),
                         ids=lambda out_of_use: out_of_use.__name__.strip("_").replace("_", " "))
def test_a_process_the_cache_is_out_of_use_for_neither_claims_nor_waits(forked, monkeypatch, a_tree, out_of_use):
    """Whatever puts the cache out of use for a process puts the claims out of use for it: it makes what it is
    asked, at once — no claim of its own while it does, no wait on a claim that stands, and that claim left alone."""
    monkeypatch.setattr(derived, "CLAIM_STUCK_AFTER_SECONDS", NO_CLAIM_IS_STUCK_SECONDS)
    _in_use(a_tree(), monkeypatch)
    asked = derived.kept(_the_claims_standing)
    assert len(asked("in use")) == 1, "the premise: in use, this derivation is made under a claim"
    another_s = _a_process_that_lives(forked)
    planted = _a_claim_planted(asked, "out of use", maker=another_s)
    kept_before = _kept_files()
    out_of_use(monkeypatch, a_tree)
    assert forked.ended(forked(lambda: asked("out of use") == [(planted.name, another_s)])) == _HELD
    assert _kept_files() == kept_before and planted.read_bytes() == another_s


# ---- a sample of what is served, made again (`derived._made_again_and_equal`) ----------------------------------------------
@pytest.fixture
def every_answer_sampled(monkeypatch):
    monkeypatch.setattr(derived, "SAMPLED_ONE_IN", 1)
    monkeypatch.setattr(derived, "SAMPLED", [])
    monkeypatch.setattr(derived, "SAMPLED_AT_MOST", 3)


def test_a_served_answer_that_is_sampled_is_made_again_and_held_equal(every_answer_sampled):
    """What every process did before there was a cache — make each derivation itself, in its own order: how a
    run-order dependence of the oracle was found — a sample of the SERVED answers still gets: made again, the cache
    off, and equal to what was served; recorded (`SAMPLED`), and no more than SAMPLED_AT_MOST a process."""
    steady, made = _counted(steady="the same whenever it is made")
    assert steady(1) == "the same whenever it is made" and len(made) == 1, "a miss is made once: nothing to sample"
    for _again in range(5):
        assert steady(1) == "the same whenever it is made"
    assert len(made) == 1 + derived.SAMPLED_AT_MOST and len(derived.SAMPLED) == derived.SAMPLED_AT_MOST
    assert all(name.endswith("answer_of") and len(key) == 2 * derived._DIGEST_BYTES for name, key in derived.SAMPLED)


def test_a_kept_answer_the_derivation_does_not_answer_now_ends_the_process_that_found_it_by_name(every_answer_sampled):
    """THE RED for a kept answer nothing ever makes again: a derivation that answers by what ran before it (here: by
    how often it was made) is frozen as its first writer made it, and served for the tree's life. Sampled, it is
    made again — and refused, by the deriver's name and the file's. So is a file that holds another answer."""
    asked, made = _counted()
    assert asked("a question") == {"made": 1}
    with pytest.raises(derived.NotWhatTheRomDerives, match=r"answer_of at .*\.pickle is NOT what the derivation answers now"):
        asked("a question")
    assert len(made) == 2 and derived.SAMPLED == []
    steady = derived.kept(lambda: "what the ROM derives")
    steady()
    planted, = (path for path in _kept_files() if derived._loaded(path.read_bytes()) == "what the ROM derives")
    planted.write_bytes(derived._stored("what another tree derived"))
    with pytest.raises(derived.NotWhatTheRomDerives):
        steady()


def test_an_answer_made_again_asks_nothing_of_the_cache_on_its_way(every_answer_sampled):
    """Made again means MADE: a derivation that asks another kept one in turn is not handed that one's kept answer
    (nor is that one sampled inside it) — the cache is off for the whole of it."""
    inner, inner_made = _counted(steady="the inner answer")
    outer = derived.kept(lambda: ("the outer answer", inner()))
    outer()
    assert len(inner_made) == 1
    assert outer() == ("the outer answer", "the inner answer")
    assert len(inner_made) == 2, "the inner derivation was served to the outer one being made again"
    assert [name.rpartition(".")[2] for name, _key in derived.SAMPLED] == ["<lambda>"], "...or sampled inside it"


def test_which_answers_are_sampled_is_decided_by_the_key_the_worker_and_the_seed(monkeypatch):
    """A few of the answers a process is served (one in SAMPLED_ONE_IN), the same ones whenever the same tree is run
    again; other ones in each xdist worker and under another SAMPLE_SEED; none once SAMPLED_AT_MOST were made."""
    monkeypatch.setattr(derived, "SAMPLED_ONE_IN", 256)
    monkeypatch.setattr(derived, "SAMPLED", [])
    keys = [derived._digest(str(nth).encode()).hex() for nth in range(64 * 256)]

    def chosen():
        return {key for key in keys if derived._sampled(key)}
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw0")
    monkeypatch.delenv(derived.SAMPLE_SEED, raising=False)
    first = chosen()
    assert 32 <= len(first) <= 128 and chosen() == first
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw1")
    another_worker_s = chosen()
    monkeypatch.setenv(derived.SAMPLE_SEED, "another day")
    assert len({frozenset(first), frozenset(another_worker_s), frozenset(chosen())}) == 3
    monkeypatch.setattr(derived, "SAMPLED", [("a deriver", "a key")] * derived.SAMPLED_AT_MOST)
    assert chosen() == set()
    monkeypatch.setattr(derived, "SAMPLED", [])
    monkeypatch.setattr(derived, "SAMPLED_ONE_IN", 0)
    assert chosen() == set()


class _WithNoEquality:
    def __init__(self, value):
        self.value = value


def test_two_answers_are_one_by_equality_or_by_what_they_pickle_to():
    """...an answer of a class that defines no `==` (two objects of it are never equal) is held by its pickle — and
    two EQUAL answers that pickle apart (one dict, filled in another order) are one by `==`."""
    assert derived._same({"a": (1, b"x")}, {"a": (1, b"x")}) and not derived._same({"a": 1}, {"a": 2})
    in_one_order, in_another = {"a": 1, "b": 2}, {"b": 2, "a": 1}
    assert pickle.dumps(in_one_order) != pickle.dumps(in_another) and derived._same(in_one_order, in_another)
    assert _WithNoEquality(1) != _WithNoEquality(1) and pickle.dumps(_WithNoEquality(1)) == pickle.dumps(_WithNoEquality(1))
    assert derived._same(_WithNoEquality(1), _WithNoEquality(1)) and not derived._same(_WithNoEquality(1), _WithNoEquality(2))


# ---- the registry's derivations made before the processes that ask for them (`derived.warm`) -------------------------------
def test_the_test_modules_are_handed_out_fewest_imports_first():
    """Every test module once — and one that imports half the suite AFTER the modules it imports (derived from the
    sources' own import lines): handed out first, a single process would derive the whole registry alone."""
    order = derived._registry_modules()
    on_disk = sorted(path.stem for path in (derived.RECREATE / "test").glob("test_*.py"))
    assert sorted(order) == on_disk and len(order) > 100
    registry = (derived.RECREATE / "test" / "test_boot_snapshot.py").read_text()
    imported = [name for name in derived._IMPORTS_A_MODULE.findall(registry) if name in on_disk]
    assert len(imported) > 50, "the premise: the registry imports the batteries"
    back = [name for name in imported
            if "test_boot_snapshot" in derived._IMPORTS_A_MODULE.findall((derived.RECREATE / "test" / f"{name}.py").read_text())]
    assert len(back) < 5, "the premise: few batteries import the registry back (those are its equals, ordered by size)"
    assert all(order.index(name) < order.index("test_boot_snapshot") for name in imported if name not in back)
    assert order.index("test_boot_snapshot") > len(order) - 10, "the registry is among the last handed out"


@pytest.fixture
def two_modules(monkeypatch):
    """`warm` over two small modules of this suite, forked from here (they are imported already: nothing is derived)."""
    monkeypatch.setattr(derived, "_registry_modules", lambda: ["test_addrs", "test_case"])
    return derived.ROOT / derived.tree_key() / derived.WARMED


def test_a_tree_is_warmed_once_and_says_so(two_modules):
    assert derived.warm(2) == "made, over 2 processes" and two_modules.is_file()
    assert derived.warm(2) == "made already for this tree"
    assert two_modules.suffix != ".pickle", "the marker is no answer"


def test_a_module_that_does_not_import_is_left_to_the_suite_and_the_tree_not_marked(two_modules, monkeypatch):
    monkeypatch.setattr(derived, "_registry_modules", lambda: ["test_addrs", "test_no_such_module_of_this_suite"])
    said = derived.warm(2)
    assert said.startswith("left to the suite to report: test_no_such_module_of_this_suite (ModuleNotFoundError")
    assert not two_modules.exists()


def test_nothing_is_warmed_with_the_cache_switched_off(two_modules, monkeypatch):
    monkeypatch.setenv(derived.DERIVED_OFF, "1")
    assert derived.warm(2) == "the cache is switched off: nothing to make" and not derived.ROOT.exists()


A_MODULE_WHOSE_IMPORT_KILLS_ITS_PROCESS = "a_module_whose_import_kills_its_process"


def test_a_fork_that_dies_warming_ends_the_pass_by_name(two_modules, monkeypatch, tmp_path):
    """THE RED for `make derived` — which every make target runs first — hung for ever by a fork that died importing
    a module (`multiprocessing.Pool` waits for the lost share): the pass ends by name, and the tree is not marked."""
    (tmp_path / f"{A_MODULE_WHOSE_IMPORT_KILLS_ITS_PROCESS}.py").write_text(
        f"import os\nos.kill(os.getpid(), {int(signal.SIGKILL)})\n")
    monkeypatch.syspath_prepend(tmp_path)
    monkeypatch.setattr(derived, "_registry_modules", lambda: ["test_addrs", A_MODULE_WHOSE_IMPORT_KILLS_ITS_PROCESS])
    with pytest.raises(fork_pool.Died, match="derived.warm: a fork DIED"):
        derived.warm(2)
    assert not two_modules.exists()


class _APoolThatBreaksAsSharesAreHandedOut:
    """A stand-in for the executor whose fork DIED while the shares were still being handed out: the `submit` of
    the share `BREAKS_AT` raises as the real one does (`concurrent.futures.process.BrokenProcessPool`)."""
    BREAKS_AT = 3

    def __init__(self, *_jobs, **_context):
        self.submitted = 0

    def __enter__(self):
        return self

    def __exit__(self, *_raised):
        return False

    def submit(self, _function, _share):
        self.submitted += 1
        if self.submitted > self.BREAKS_AT:
            raise fork_pool.BrokenProcessPool("a child process terminated abruptly")
        return fork_pool.concurrent.futures.Future()


def test_a_fork_that_dies_while_the_shares_are_handed_out_is_a_death_by_name(monkeypatch):
    """RED before the shares were submitted inside the `try` (seen once in fifteen full runs, as
    `test_fork_pool`'s death case: a bare BrokenProcessPool out of `pool.submit`, the pass — `make bench`'s measuring
    pass — ended unnamed): a pool that breaks under the fourth `submit` ends the pass as `Died`, naming every share
    that has no answer — the ones handed out and the ones never handed out."""
    monkeypatch.setattr(fork_pool.concurrent.futures, "ProcessPoolExecutor", _APoolThatBreaksAsSharesAreHandedOut)
    with pytest.raises(fork_pool.Died, match=r"the bench: a fork DIED before it answered .* 9 of 9 shares never came back, the first 0"):
        fork_pool.over_forks(abs, range(9), 2, 1, "the bench")
