"""ROM-ONLY DERIVATIONS, KEPT ON DISK BY CONTENT (`@kept`).

WHAT IS KEPT. A battery's machines are DERIVED: the ROM's own runs — a scenario watched at a layer's entries, a
file-selector session over the staged disk, the one run that says whether a row's routine stores the Line-F mask word.
A derivation reads the ROM, the boot snapshot and its own arguments and runs no line of the reconstruction, so its
answer is the same in every process of a run and in every run of the same tree — and every process made it again:
each xdist worker, the bench, each `make` of the three gates (25 CPU-seconds of every process's import, measured).
`@kept` keeps a derivation's answer in `build/derived/`, and serves it to the next process that asks the same question.

A STALE ANSWER IS NOT SERVED, BY CONSTRUCTION, because "the same question" is decided by CONTENT, never by a name, a
version number someone remembers to bump, or a file's date:
  * THE TREE (`tree_key`): the digest of every file a derivation could read or be made by — every source, header and
    Python file of this project (the tests, the bench, the tools), the kit's Python and the workspace tools it
    imports, the ROM image, the boot snapshots, the oracle's library and the candidate's AS THIS PROCESS LOADED IT,
    the project's and the kit's makefiles — with the interpreter's version and whether it runs its `assert`s. An
    edit to ANY of them, a comment's included, is another tree: nothing derived under the old one is found. That is
    deliberately wider than what a derivation reads (the deriving code's own version is these files), and what it
    costs is honest: an edited tree derives everything again, once.
  * THE BASE IMAGE in force when the question is asked (`harness.set_base_image`: the snapshot, or another capture's
    under the sweep that proves no row depends on an unreproducible byte) — its digest, not its name.
  * THE DERIVING FUNCTION, read as any function argument is (below): its name is not enough — two lambdas of one
    line, two closures of one `def`, have one name.
  * ITS ARGUMENTS, BY VALUE (`fingerprint`): numbers, strings, bytes, tuples, lists, dicts, sets, named tuples,
    `struct.Struct`s and ranges by their content; a machine's POKES by the image they make (`_of_pokes`); a FUNCTION
    by its code, its defaults, its attributes and — the part that differs between two closures of one `def` — the
    values its closure holds, recursively; a bound method and a `functools.partial` by their parts, a
    `functools.cache`d function by the one it wraps; an object of a class that says what a derivation is asked about
    of it (`ASKED_ABOUT`) by that. An argument of any other kind is REFUSED by name: a derivation is not kept on the
    strength of an object nobody can read.

THE KEY NAMES THE TREE THIS PROCESS IS MADE OF — the part no digest gives, because three agents edit this tree while
runs are in flight, and a process is the files it has ALREADY read. A key made of the files as they are when the
first derivation is asked would name the tree AFTER an edit while the process runs the modules it imported BEFORE it —
and what such a process keeps is served to every later process of the edited tree (measured: an edit 0.3 s into a
worker's life, the old helper's answer served under the new tree's key, for as long as that tree lived). So:
  * WHEN THIS PROCESS BEGAN is asked of the kernel (`_began_ns`), and a file of the tree CHANGED SINCE — by its
    modification date or by its inode's — puts the cache out of use for the process's whole life: whichever of its
    modules was read before the change and whichever after, it never keeps and is never served. (A process this
    module cannot ask that of keeps nothing either.)
  * THE FILES ARE FOUND AND STAMPED AS THIS MODULE IS IMPORTED (`_AS_FOUND`: size, modification date, inode date),
    and this module is imported FIRST — `conftest.py`'s first import, the bench's, this file's own `__main__` — before
    any module that derives. The key's bytes are read later, at the first question, and are these stamps' bytes or
    the process is out (`_Tree`).
  * BEFORE EVERY WRITE the process asks again, exactly (`_Tree.still`): every file as it was stamped, no file
    added or gone, no module of this repository imported that the key does not read (`unkeyed_modules`: the list
    of patterns is HELD to what is really imported, not trusted). And BEFORE A READ the same, at most every
    STILL_ASKED_EVERY_SECONDS and at once when a module was imported since the last time — a helper edited under a
    running process and imported late is not answered by the tree before the edit.
Once out, a process stays out (said once, on stderr, with the reason).

WHAT A DERIVATION MUST BE to be decorated: a function of its arguments, the ROM, the base image and the tree alone —
no candidate code, nothing read from a module's state that a test changes, no effect a caller relies on but its
answer (a hit runs nothing). Its answer must pickle. The kit seeds every register a run begins with (the user stack
pointer too, since the kit's own commit of that), so a derivation answers one machine whatever ran before it.

HELD TO IT ON EVERY RUN (`_made_again_and_equal`). A kept answer is made once per tree, so what every process once
did by itself — make each derivation again, in its own import order, which is how a run-order dependence of the
oracle was found — would be done by nobody. So each process makes a SAMPLE of the answers it is served again, the
cache off, and holds each equal to what it was served: a few per process (SAMPLED_AT_MOST), chosen by the key, the
xdist worker's name and SAMPLE_SEED — other answers in each worker, the same ones on the same tree. A kept answer the
ROM does not derive now ends the process that found it, by name.

UNDER XDIST every worker asks the same questions at once: a file is written whole under another name and renamed
into place (`os.replace`), so a reader finds an answer or none — never half of one — and ten workers that derive the
same thing write the same bytes. EVERY kept file carries the digest of what it holds: a file that will not load, or
does not hold what its digest says (a disk that filled, a flipped bit, an interpreter's pickle of another day), is
not an answer — the derivation is made again and the file replaced.

SWITCHED OFF by DERIVED_OFF in the environment (nothing read, nothing written: every derivation made, as before
there was a cache) — the cold shore of the A/B the cache is held equal by — and for a process whose candidate is not
the project's own build (a mutation sweep's private library: each mutant would be a tree of its own, written once
and never read). `make clean` removes `build/`, and the cache with it; a tree nobody used for PRUNE_AFTER_SECONDS,
or past the TREES_KEPT most lately used, goes when a process first writes to another.
"""
import contextlib
import ctypes
import fnmatch
import functools
import hashlib
import importlib
import os
import pickle
import re
import shutil
import struct
import sys
import time
import types
import zlib
from pathlib import Path

RECREATE = Path(__file__).resolve().parents[1]
REPO = RECREATE.parents[2]
KIT = REPO / "tools" / "recreate_kit"
ROOT = RECREATE / "build" / "derived"
DERIVED_OFF = "AES_DERIVED_OFF"
HANDED_DOWN = "AES_DERIVED_TREE"        # INTERNAL: a process's tree key and the record it was made with, for its children
SAMPLE_SEED = "AES_DERIVED_SAMPLE_SEED"
PRUNE_AFTER_SECONDS = 2 * 24 * 3600
TREES_KEPT = 6                          # this process's and the five most lately used beside it
# EVERY FILE A DERIVATION COULD READ OR BE MADE BY, as glob patterns under the project and under the kit. The
# candidate's library is not among them: it is the file this process LOADED (`_candidate`), wherever that is. HELD to
# what a process really imports (`unkeyed_modules`): a module of this repository these do not find puts the cache out
# of use for the process that imported it.
PROJECT_INPUTS = ("test/*.py", "bench/*.py", "tools/*.py", "include/*.h", "include/*/*.h", "src/*.c", "src/*/*.c",
                  "src/*.S", "src/*/*.S", "atari/*.mk", "atari/shim_include/*.h", "build/boot_ram*.bin", "project.toml",
                  "Makefile", "requirements.txt", "../names.txt", "../aes_map/*.py")
KIT_INPUTS = ("*.py", "oracle/*.py", "oracle/build/liboracle.so", "include/*.h", "src/*.c", "kit.mk",
              "../hatari/TOS102US.img", "../*.py")
FEWEST_INPUTS = 300                     # the suite alone is more files than this: fewer means the patterns found nothing
STILL_ASKED_EVERY_SECONDS = 0.05        # how long a READ may rest on the last time the tree was asked whether it moved
_DIGEST_BYTES = 20
_LENGTH_BYTES = 8                       # a digest's part is counted, in this many bytes, before it is read
_SHARD_CHARACTERS = 2                   # a kept file lies in the directory its key's first characters name
_SHOWN_CHARACTERS = 80                  # of a value or a reason quoted in a message


def _digest(*parts):
    digest = hashlib.sha256()
    for part in parts:
        digest.update(len(part).to_bytes(_LENGTH_BYTES, "big"))
        digest.update(part)
    return digest.digest()[:_DIGEST_BYTES]


# ---- when this process began -----------------------------------------------------------------------------------------
_CTL_KERN, _KERN_PROC, _KERN_PROC_PID = 1, 14, 1        # <sys/sysctl.h>: the kernel's record of one process, by pid
_KINFO_PROC_BYTES = 648                                 # sizeof(struct kinfo_proc), Darwin's 64-bit
_STARTED = struct.Struct("@qi")                         # ...which BEGINS with the process's start: a timeval
_NS_PER_SECOND, _NS_PER_MICROSECOND = 10 ** 9, 10 ** 3


def _began_ns():
    """When THIS process began, by the kernel's own record — nanoseconds since the epoch, the clock a file's dates are
    kept by — or None where this module does not know how to ask (anything but Darwin: such a process keeps nothing).
    A fork inherits its parent's answer, and means it: its modules are the ones the parent read."""
    if sys.platform != "darwin":
        return None
    libc = ctypes.CDLL(None, use_errno=True)
    name = (ctypes.c_int * 4)(_CTL_KERN, _KERN_PROC, _KERN_PROC_PID, os.getpid())
    record = ctypes.create_string_buffer(_KINFO_PROC_BYTES)
    size = ctypes.c_size_t(_KINFO_PROC_BYTES)
    if libc.sysctl(name, len(name), record, ctypes.byref(size), None, 0) != 0 or size.value != _KINFO_PROC_BYTES:
        return None
    seconds, microseconds = _STARTED.unpack_from(record.raw)
    return seconds * _NS_PER_SECOND + microseconds * _NS_PER_MICROSECOND


# ---- the tree's files --------------------------------------------------------------------------------------------------
def _candidate():
    """The candidate library this process loaded."""
    import harness                      # here, not above: this module is imported before anything that derives
    return Path(harness._lib._name).resolve()


def _entries(directory):
    try:
        with os.scandir(directory) as scanned:
            return list(scanned)
    except OSError:
        return []


def _matching(root, pattern):
    """The files under `root` that `pattern` names: its directories literal or `*` (every directory there), its last
    part a file's name pattern. (`Path.glob` answers the same, ten times slower — and every child process asks.)"""
    *directories, name = pattern.split("/")
    places = [str(root)]
    for part in directories:
        if part == "*":
            places = [entry.path for place in places for entry in _entries(place) if entry.is_dir()]
        else:
            places = [os.path.join(place, part) for place in places]
    return [os.path.normpath(entry.path) for place in places for entry in _entries(place)
            if fnmatch.fnmatchcase(entry.name, name) and entry.is_file()]


def input_files(project=RECREATE, kit=KIT):
    """Every file the tree's key is the digest of, the candidate's library aside: sorted, each once."""
    found = {path for pattern in PROJECT_INPUTS for path in _matching(project, pattern)}
    found |= {path for pattern in KIT_INPUTS for path in _matching(kit, pattern)}
    return [Path(path) for path in sorted(found)]


def digest_of_files(files, relative_to):
    """The digest of `files` — each one's path below `relative_to` (a file moved or renamed is another tree) and its
    bytes."""
    parts = []
    for path in files:
        parts += [os.path.relpath(path, relative_to).encode(), path.read_bytes()]
    return _digest(*parts)


_STAMP_DATES = slice(1, 3)             # of a stamp `(size, modification date, inode date)`: its two dates


def _stamps(files):
    """Each file's size, modification date and inode date, as the file system holds them now (None: no such file).
    The inode's date too: it moves with every write and no `utime` sets it back."""
    stamps = []
    for path in files:
        try:
            status = os.stat(path)
        except OSError:
            stamps.append(None)
        else:
            stamps.append((status.st_size, status.st_mtime_ns, status.st_ctime_ns))
    return stamps


def _changed_since(began_ns, files, stamps):
    """The first of `files` whose `stamps` say it changed at or after `began_ns` (by either date) — or None."""
    for path, stamp in zip(files, stamps):
        if stamp is not None and max(stamp[_STAMP_DATES]) >= began_ns:
            return path
    return None


_REAL_PATHS = {}                        # {a module's file as it names it: the file} — asked of every module, often


def _real(path):
    if path not in _REAL_PATHS:
        _REAL_PATHS[path] = os.path.realpath(path)
    return _REAL_PATHS[path]


def _file_below(module, root):
    """The file `module` was read from, where it lies below `root` (a module the interpreter found through a link
    out of it — the virtual environment's — does not) — else None."""
    file = getattr(module, "__file__", None)
    if not file or file.startswith("<"):        # none, or no file at all: a script read from `<stdin>`
        return None
    file = _real(file)
    return file if file.startswith(str(root) + os.sep) else None


def repository_modules(root=REPO):
    """The file of every module this process has imported out of this repository, sorted."""
    return sorted({file for file in (_file_below(module, root) for module in list(sys.modules.values())) if file})


def unkeyed_modules(files=None, root=REPO):
    """The modules of this repository this process imported that the tree's key does NOT read — `files`: the key's
    (`input_files()` by default). Every one is a file a derivation could be made by and no key would notice an edit of."""
    keyed = {str(path) for path in (input_files() if files is None else files)}
    return [file for file in repository_modules(root) if file not in keyed]


def _found():
    """The tree's files and their stamps, now."""
    files = input_files()
    return files, _stamps(files)


# THE TREE AS THIS PROCESS FOUND IT — and when the process began, and which modules of this repository it had imported
# by then (the suite's `conftest.py`, the kit's plugins named on the command line: none that derives, `test_derived.py`
# holds). This module's first act, before any import of the project's or the kit's.
_BEGAN_NS = _began_ns()
LOADED_BEFORE = repository_modules()
_AS_FOUND = _found()


class _Tree:
    """THIS PROCESS'S TREE (the module's docstring: the key names the tree the process is made of): the files as the
    process found them when it was new, its key — and `moved`, the reason nothing is kept for it or served to it, as
    soon as there is one. Made of: `listing()`, the tree's files now; `found`, their list and stamps as the process
    found them; `began_ns`, when it began; `candidate`, the library it loaded; `root`, the repository its modules
    are read out of.

    A CHILD of a process that made the key (a guard's fresh interpreter: hundreds a run) is handed it in the
    environment WITH the digest of that record (HANDED_DOWN), and takes the key without reading a file's bytes only
    where its own record, made now, is that one — every input file as its parent found it, under the same
    interpreter. Anything else, and the child reads the tree for itself."""

    def __init__(self, listing, found, began_ns, candidate, root=REPO):
        self._listing, self._root, self.began_ns = listing, root, began_ns
        self.listed, stamps = found
        assert len(self.listed) >= FEWEST_INPUTS, (
            f"the tree's key reads {len(self.listed)} files: its patterns no longer find the tree")
        self.files = [*self.listed, candidate]
        self.stamps = [*stamps, *_stamps([candidate])]
        self._stamp_of = dict(zip(map(str, self.files), self.stamps))
        self.key = self.moved = None
        self._asked_at, self._modules_then = time.monotonic(), 0
        if not self._still(self._why_not_the_tree_it_began_with() or self._why_moved()):
            return
        interpreter = f"{sys.version} -O{sys.flags.optimize}".encode()
        recorded = _digest(repr(self.files).encode(), repr(self.stamps).encode(), interpreter).hex()
        key, _, as_recorded = os.environ.get(HANDED_DOWN, "").partition(":")
        if as_recorded != recorded:
            key = _digest(digest_of_files(self.listed, root), candidate.read_bytes(), interpreter).hex()
            if not self.still():        # ...the bytes just read are the ones the stamps are of, or there is no key
                return
            os.environ[HANDED_DOWN] = f"{key}:{recorded}"
        self.key = key

    def _why_not_the_tree_it_began_with(self):
        """Why the files as found are not known to be the ones this process's modules were read from — or None."""
        if self.began_ns is None:
            return "this process cannot be asked when it began (`derived._began_ns`)"
        changed = _changed_since(self.began_ns, self.files, self.stamps)
        return f"{changed} changed after this process began" if changed else None

    def _why_changed(self):
        """Why a file of the tree is not as this process found it — or None."""
        for path, was, now in zip(self.files, self.stamps, _stamps(self.files)):
            if was != now:
                return f"{path} changed under this process"
        return None

    def _why_moved(self):
        """Why the tree is no longer the one this process found — a file changed, added or gone, a module imported
        that the key does not read — or None. ASKED EXACTLY: every file, the tree's listing, every module."""
        listed = self._listing()
        if listed != self.listed:
            return f"{sorted(set(listed) ^ set(self.listed))[0]} was added to the tree, or left it, under this process"
        unkeyed = unkeyed_modules(self.listed, self._root)
        if unkeyed:
            return (f"this process imported {unkeyed[0]}, which the tree's key does not read "
                    f"(`derived.PROJECT_INPUTS` / `KIT_INPUTS`)")
        return self._why_changed()

    def _why_a_module_imported_since_is_not_the_tree_s(self):
        """Why a module imported since the tree was last asked is not one of the tree as found — its file not the
        key's, or changed since — or None. (`sys.modules` keeps the order its modules came in.)"""
        modules = list(sys.modules.values())
        if len(modules) < self._modules_then:
            return self._why_moved()
        for module in modules[self._modules_then:]:
            file = _file_below(module, self._root)
            if file is None:
                continue
            if file not in self._stamp_of:
                return f"this process imported {file}, which the tree's key does not read"
            if _stamps([file]) != [self._stamp_of[file]]:
                return f"{file} changed under this process, and was imported after"
        return None

    def _still(self, why_not):
        """Record that the tree was asked now, and `why_not` it is this process's still (None: it is)."""
        self._asked_at, self._modules_then = time.monotonic(), len(sys.modules)
        if why_not and not self.moved:
            self.moved = why_not
            print(f"derived: {self.moved} — this process keeps and reads nothing more", file=sys.stderr)
        return not self.moved

    def still(self):
        """Is the tree, NOW, the one this process found (`_why_moved`: asked exactly)? Once it is not, never again
        for this process."""
        return not self.moved and self._still(self._why_moved())

    def lately_still(self):
        """`still`, for a READ, at a read's price: every module imported since the last time asked about at once
        (code read off the tree as it is NOW), every file's stamp again once STILL_ASKED_EVERY_SECONDS have gone by."""
        if self.moved:
            return False
        if len(sys.modules) != self._modules_then:
            return self._still(self._why_a_module_imported_since_is_not_the_tree_s())
        if time.monotonic() - self._asked_at >= STILL_ASKED_EVERY_SECONDS:
            return self._still(self._why_changed())
        return True


@functools.cache
def _tree():
    return _Tree(input_files, _AS_FOUND, _BEGAN_NS, _candidate())


def tree_key():
    """THE TREE's key (the module's docstring): hex, the name of this tree's directory under ROOT — None for a
    process the cache is out of use for (`_Tree.moved`)."""
    return _tree().key


# ---- the base image ----------------------------------------------------------------------------------------------------
_BASE_DIGESTS = {}                      # {id(a base image): (the image, its digest)} — the image held, so its id is its own


def image_key(image):
    """The digest a base image is known by."""
    return _digest(bytes(image))


def base_key():
    """The digest of the base image a derivation made NOW would run over (`harness.set_base_image`'s)."""
    import harness                      # here, not above: this module is imported before anything that derives
    base = harness.differential_base()
    held = _BASE_DIGESTS.get(id(base))
    if held is None or held[0] is not base:
        held = _BASE_DIGESTS[id(base)] = (base, image_key(base))
    return held[1]


# ---- an argument, by value ---------------------------------------------------------------------------------------------
class Unreadable(TypeError):
    """An argument `fingerprint` cannot read by value."""


# AN OBJECT OF A CLASS OF THE TREE'S is read by what the class SAYS a derivation is asked about: a method of this
# name, answering a readable value (a schedule: its rows and its entry — not how far the last run counted).
ASKED_ABOUT = "derived_content"


_EMPTY_CELL = "a closure's cell nothing was stored in yet"


def _cell(cell):
    try:
        return cell.cell_contents
    except ValueError:
        return _EMPTY_CELL


def _of_function(function, seen):
    code = function.__code__
    cells = tuple(_cell(cell) for cell in function.__closure__ or ())
    return _of(("function", function.__module__, function.__qualname__, code, function.__defaults__,
                function.__kwdefaults__, dict(vars(function)), dict(zip(code.co_freevars, cells))), seen)


def _of_code(code, seen):
    return _of(("code", code.co_name, code.co_firstlineno, code.co_code, code.co_consts, code.co_names,
                code.co_varnames, code.co_freevars), seen)


_BYTES_LIKE = (bytes, bytearray, memoryview)
_POKE_HEADER = struct.Struct(">qQ")     # a run's address and its length


def _is_pokes(value):
    return bool(value) and all(type(at) is int and isinstance(data, _BYTES_LIKE) for at, data in value.items())


def _of_pokes(pokes):
    """A machine's pokes — `{address: bytes}`, a megabyte in thousands of runs for a session's — BY THE IMAGE THEY
    MAKE, in one pass. Runs that do not overlap make one image in any order, so they are read in address order: each
    run's address, length and bytes (two dicts built in another order are one question; two that cut the same bytes
    into other runs are two — a derivation is asked about its argument). Runs that OVERLAP are laid one over another
    in the dict's own order (`make_image`), and that order then decides the image: they are read in it, and are no
    question a dict of the same runs in another order asks."""
    in_order = sorted(pokes)
    overlap = any(at + len(pokes[at]) > after for at, after in zip(in_order, in_order[1:]))
    digest = hashlib.sha256(b"pokes, as laid" if overlap else b"pokes")
    for at in (pokes if overlap else in_order):
        data = pokes[at]
        digest.update(_POKE_HEADER.pack(at, len(data)))
        digest.update(data)
    return digest.digest()[:_DIGEST_BYTES]


def _of(value, seen):
    """`value`'s canonical bytes: its kind, then its content — `seen` the containers and functions on the way down (a
    function whose closure reaches itself is named by its place, not walked for ever)."""
    if value is None or isinstance(value, (bool, int, float, str, bytes)):
        return _digest(type(value).__name__.encode(), repr(value).encode())
    if isinstance(value, (bytearray, memoryview)):
        return _digest(b"bytes-like", bytes(value))
    if isinstance(value, (struct.Struct, range)):
        return _digest(type(value).__name__.encode(), repr(value.format if isinstance(value, struct.Struct) else value).encode())
    if id(value) in seen:
        return _digest(b"seen", str(seen.index(id(value))).encode())
    seen = seen + [id(value)]
    if isinstance(value, (tuple, list)):
        kind = type(value).__qualname__ if hasattr(value, "_fields") else type(value).__name__
        return _digest(kind.encode(), *(_of(each, seen) for each in value))
    if isinstance(value, dict):
        if _is_pokes(value):
            return _of_pokes(value)
        items = sorted((_of(key, seen), _of(each, seen)) for key, each in value.items())
        return _digest(b"dict", *(part for item in items for part in item))
    if isinstance(value, (set, frozenset)):
        return _digest(b"set", *sorted(_of(each, seen) for each in value))
    if isinstance(value, types.FunctionType):
        return _of_function(value, seen)
    if isinstance(value, types.CodeType):
        return _of_code(value, seen)
    if isinstance(value, types.MethodType):
        return _digest(b"method", _of(value.__func__, seen), _of(value.__self__, seen))
    if isinstance(value, functools.partial):
        return _digest(b"partial", _of(value.func, seen), _of(value.args, seen), _of(value.keywords, seen))
    if isinstance(getattr(value, "__wrapped__", None), types.FunctionType):     # `functools.cache`'s wrapper, `kept`'s
        return _digest(b"wrapper", type(value).__qualname__.encode(), _of(value.__wrapped__, seen))
    if hasattr(type(value), ASKED_ABOUT):
        return _digest(b"object", f"{type(value).__module__}.{type(value).__qualname__}".encode(),
                       _of(getattr(value, ASKED_ABOUT)(), seen))
    raise Unreadable(f"{type(value).__module__}.{type(value).__qualname__} ({repr(value)[:_SHOWN_CHARACTERS]}) cannot "
                     f"be read by value: a derivation is kept by the content of its arguments (`derived.fingerprint`)")


def fingerprint(value):
    """`value` BY VALUE, as a digest (the module's docstring says what of each kind) — `Unreadable` for a kind it does
    not read."""
    return _of(value, [])


# ---- the files ---------------------------------------------------------------------------------------------------------
@functools.cache
def _candidate_is_the_project_s():
    return _candidate().parent == (RECREATE / "build").resolve()


_MADE_AGAIN_NOW = []                    # non-empty while a served answer is made again (`_made_again_and_equal`)


def switched_off():
    """Is nothing kept for this process, now — said so in the environment, its candidate not the project's own build,
    its tree not the one it began with or no longer the one it found, or a served answer being made again?"""
    return (bool(os.environ.get(DERIVED_OFF)) or bool(_MADE_AGAIN_NOW) or not _candidate_is_the_project_s()
            or not _tree().lately_still())


@functools.cache
def _prune_trees_nobody_uses(mine):
    """ONCE PER PROCESS, as it first writes to its tree `mine`: of the OTHER trees' directories, those not used for
    PRUNE_AFTER_SECONDS go, and those past the TREES_KEPT most lately used (every edit of the tree is a tree: an
    afternoon's work would otherwise keep a hundred)."""
    oldest = time.time() - PRUNE_AFTER_SECONDS
    with contextlib.suppress(OSError):
        others = sorted(((other.stat().st_mtime, other) for other in ROOT.iterdir() if other != mine and other.is_dir()),
                        reverse=True)
        for nth, (used, other) in enumerate(others):
            if used < oldest or nth >= TREES_KEPT - 1:
                shutil.rmtree(other, ignore_errors=True)


def _path_of(key):
    return ROOT / tree_key() / key[:_SHARD_CHARACTERS] / f"{key}.pickle"


# A kept file: one byte saying how the pickle is stored, the digest of what follows it, then the pickle — PACKED
# (zlib's fastest level) where it is large: a session's machine is a megabyte of mostly empty RAM, and eighty of them a
# tree would be most of the cache's size. THE DIGEST IS EVERY FILE'S, the small plain ones' too: a pickle with one bit
# flipped is, one time in five, another answer that loads (measured: 57 of 300).
PLAIN, PACKED = b"P", b"Z"
PACKED_FROM_BYTES = 1 << 16
FASTEST = 1
_HEADER_BYTES = len(PLAIN) + _DIGEST_BYTES


def _stored(answer):
    """`answer` as a kept file's bytes."""
    data = pickle.dumps(answer, protocol=pickle.HIGHEST_PROTOCOL)
    how, held = (PACKED, zlib.compress(data, FASTEST)) if len(data) >= PACKED_FROM_BYTES else (PLAIN, data)
    return how + _digest(held) + held


def _loaded(stored):
    """The answer a kept file's bytes hold — an exception for bytes that are no kept file's, or not the ones its
    digest is of."""
    how, digest, held = stored[:len(PLAIN)], stored[len(PLAIN):_HEADER_BYTES], stored[_HEADER_BYTES:]
    if how not in (PLAIN, PACKED) or digest != _digest(held):
        raise ValueError("not a kept answer")
    return pickle.loads(zlib.decompress(held) if how == PACKED else held)


def _read(path):
    """The answer kept at `path`, as `(True, answer)` — `(False, None)` where there is none, or none that loads."""
    try:
        return True, _loaded(path.read_bytes())
    except FileNotFoundError:
        return False, None
    except Exception:                   # not an answer: made again, and replaced
        return False, None


def _write(path, data):
    """`data` at `path`, whole or not at all: written beside it under a name of this process's own, then renamed —
    and not at all by a process whose tree is no longer the one it found (`_Tree.still`, asked exactly, now)."""
    if not _tree().still():
        return
    tree = ROOT / tree_key()
    path.parent.mkdir(parents=True, exist_ok=True)
    scratch = path.with_name(f"{path.name}.{os.getpid()}.{time.monotonic_ns()}.part")
    try:
        scratch.write_bytes(data)
        os.replace(scratch, path)
    finally:
        with contextlib.suppress(OSError):
            scratch.unlink()
    with contextlib.suppress(OSError):
        os.utime(tree)                  # in use: no other process prunes it
    _prune_trees_nobody_uses(tree)


@functools.cache
def _in_use(tree):
    """ONCE PER PROCESS that was served an answer of `tree`: its directory dated now, so no other process prunes it."""
    with contextlib.suppress(OSError):
        os.utime(tree)


def key_of(derive, arguments, named):
    """The key of `derive(*arguments, **named)` asked NOW: the base image, the function, the arguments — hex. (The
    tree is the directory it is looked for in.)"""
    return _digest(base_key(), fingerprint(derive), fingerprint(arguments), fingerprint(named)).hex()


# ---- a sample of what is served, made again (the module's docstring: HELD TO IT ON EVERY RUN) -----------------------------
SAMPLED_ONE_IN = 256                    # of the answers a process is served (a worker's registry import: some 900)
SAMPLED_AT_MOST = 4                     # ...and no more than this many a process: seconds of ROM runs, not the import again
SAMPLED = []                            # what this process made again and found equal: (the deriver's name, the key)
_CHOSEN_BYTES = 4


class NotWhatTheRomDerives(AssertionError):
    """A kept answer is not what its derivation answers now."""


def _sampled(key):
    """Is the answer under `key` one this process makes again? By the key, this process's xdist worker and
    SAMPLE_SEED — nothing else, so the same run of the same tree samples the same answers."""
    if not SAMPLED_ONE_IN or len(SAMPLED) >= SAMPLED_AT_MOST:
        return False
    salt = f"{os.environ.get('PYTEST_XDIST_WORKER', '')}:{os.environ.get(SAMPLE_SEED, '')}".encode()
    return int.from_bytes(_digest(key.encode(), salt)[:_CHOSEN_BYTES], "big") % SAMPLED_ONE_IN == 0


def _same(one, the_other):
    """Are two answers one? By `==`, or — objects of a class that defines none — by what they pickle to."""
    with contextlib.suppress(Exception):
        if one == the_other:
            return True
    return pickle.dumps(one, protocol=pickle.HIGHEST_PROTOCOL) == pickle.dumps(the_other, protocol=pickle.HIGHEST_PROTOCOL)


def _made_again_and_equal(derive, arguments, named, key, served):
    """`derive(*arguments, **named)` MADE AGAIN, the cache off for everything it asks in turn, and held equal to the
    answer `served` under `key`."""
    _MADE_AGAIN_NOW.append(key)
    try:
        again = _loaded(_stored(derive(*arguments, **named)))
    finally:
        _MADE_AGAIN_NOW.pop()
    if not _same(again, served):
        raise NotWhatTheRomDerives(
            f"derived: the answer kept for {derive.__module__}.{derive.__qualname__} at {_path_of(key)} is NOT what "
            f"the derivation answers now, made again in this process — a derivation that depends on what ran before "
            f"it, or on something its key does not read, or a kept file from another tree. Nothing served from "
            f"{ROOT / tree_key()} can be trusted: `make clean`, and find which.")
    SAMPLED.append((f"{derive.__module__}.{derive.__qualname__}", key))


def kept(derive):
    """DECORATE A ROM-ONLY DERIVATION (the module's docstring: what it must be): its answer is read from
    `build/derived/` where this tree, this base image and these arguments were asked before — by any process — and
    made, kept and answered where they were not."""
    @functools.wraps(derive)
    def asked(*arguments, **named):
        if switched_off():
            return derive(*arguments, **named)
        key = key_of(derive, arguments, named)
        path = _path_of(key)
        found, answer = _read(path)
        if found:
            _in_use(ROOT / tree_key())
            if _sampled(key):
                _made_again_and_equal(derive, arguments, named, key, answer)
            return answer
        stored = _stored(derive(*arguments, **named))
        _write(path, stored)
        return _loaded(stored)          # ...what a hit answers, to the byte: a miss is not another object's shape
    asked.derive = derive
    return asked


# ---- THE REGISTRY'S DERIVATIONS MADE BEFORE THE PROCESSES THAT WILL ALL ASK FOR THEM (`python test/derived.py`) ---------
# A cold tree's first run would have every xdist worker, and the bench beside them, make the same derivations at the
# same time — each for itself, twenty-five seconds of import apiece, because none has finished when the others ask. So
# the makefile runs this first: the test modules — whose import IS the registry's derivations — imported by a few
# forks of this process side by side, each taking the next module nobody has yet (the long ones first). What they
# derive is kept as it is made, so the processes that follow are served. A tree warmed once says so (WARMED, in its
# own directory) and costs the next `make` the price of reading the tree's key. Nothing here decides anything: a
# module that will not import is left for the suite to report, and with the cache switched off there is nothing to do.
# A fork that DIES, or a pass that stops coming back, ends the pass by name (`fork_pool`) — and `make` with it.
WARMED = "warmed"
# How long the pass may go with no module coming back. The longest module's import, cold and ten forks side by side,
# is 22 s on a quiet machine (the registry's own: measured 2026-10-07); forty times that — three agents' suites
# beside it have been measured at a load of 190 on ten cores.
LONGEST_IMPORT_SECONDS = 22
WARM_STUCK_AFTER_SECONDS = 40 * LONGEST_IMPORT_SECONDS


_IMPORTS_A_MODULE = re.compile(r"^\s*(?:import|from)\s+(\w+)", re.MULTILINE)


def _registry_modules():
    """The test modules, by name, in the order they are handed out: the ones that import FEWEST other modules of
    `test/` first (counted through what those import in turn), the larger first among equals. A module that imports
    half the suite — the bench's registry, the door's own tests — then comes last, when what it imports has been
    derived by the processes that took its parts; handed out first, one process would derive the whole registry
    alone while the others made the same things beside it."""
    sources = {path.stem: path for path in (RECREATE / "test").glob("*.py")}
    imports = {name: {found for found in _IMPORTS_A_MODULE.findall(path.read_text()) if found in sources and found != name}
               for name, path in sources.items()}

    def reached(name, seen):
        for found in imports[name] - seen:
            seen.add(found)
            reached(found, seen)
        return seen
    weight = {name: len(reached(name, set())) for name in sources}
    return sorted((name for name in sources if name.startswith("test_")),
                  key=lambda name: (weight[name], -sources[name].stat().st_size))


def _imported(name):
    """IN A FORK: the module `name` imported; what it raised, if it did (the suite's to report, not this pass's)."""
    try:
        importlib.import_module(name)
    except BaseException as raised:    # a SystemExit of a module's own too: this pass decides nothing
        return name, f"{type(raised).__name__}: {raised}"
    return name, None


def warm(jobs):
    """Make the registry's derivations for this tree, over `jobs` processes, unless they were made (WARMED): what was
    done, in a word."""
    import fork_pool

    if switched_off():
        return "the cache is switched off: nothing to make"
    marker = ROOT / tree_key() / WARMED
    if marker.exists():
        return "made already for this tree"
    made = fork_pool.over_forks(_imported, _registry_modules(), jobs, WARM_STUCK_AFTER_SECONDS, "derived.warm")
    failed = [(name, why) for name, why in made.values() if why]
    if failed:
        return "left to the suite to report: " + "; ".join(f"{name} ({why[:_SHOWN_CHARACTERS]})" for name, why in failed)
    if _tree().still():
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
    return f"made, over {jobs} processes"


if __name__ == "__main__":
    import derived                      # the module the batteries import: this file run as a script is another object
    print(f"derived: {derived.warm(os.cpu_count())}")
